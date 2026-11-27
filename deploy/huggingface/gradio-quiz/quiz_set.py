"""Compose a bounded quiz set inside one GPU allocation, using SMGS validators."""
import time
import logging
from app.engine import ChatFailure
from app.studio import english_question
from grounded_quiz import evidence_passages, generate_grounded_question
from quiz_quality import DiversityGuard, evidence_order, question_guidance


ENGLISH_STEMS = {
    'purpose': 'What was this object used for?',
    'material': 'What material is the object made of?',
    'technique': 'Which technique was used to make this object?',
    'decoration': 'What kind of decoration does the object have?',
    'shape': 'How is the object shaped?',
}


class DeadlineEngine:
    def __init__(self, engine, deadline, clock):
        self.engine, self.deadline, self.clock = engine, deadline, clock
        self.lock = engine.lock

    def generate_json(self, prompt, validator, **kwargs):
        remaining = self.deadline - self.clock()
        if remaining < 1:
            raise ChatFailure('Đã hết thời gian tạo bộ câu hỏi trong lượt GPU này.', 504)
        kwargs['deadline_seconds'] = min(kwargs.get('deadline_seconds') or remaining, remaining)
        return self.engine.generate_json(prompt, validator, **kwargs)


def generate_quiz_set(engine, name, source, difficulty, excluded, count=5, *, language='vi', budget_seconds=85, clock=time.monotonic):
    if type(count) is not int or count not in (1, 3, 5):
        raise ValueError('Chọn bộ 1, 3 hoặc 5 câu hỏi.')
    if language not in ('vi', 'en'):
        raise ValueError('Unsupported draft language')
    bounded = DeadlineEngine(engine, clock() + budget_seconds, clock)
    questions, warnings, used_evidence = [], [], []
    passages = evidence_passages(source)
    order = evidence_order(passages, name, excluded)
    guard = DiversityGuard(name, excluded)
    calls, max_calls, last_error, fatal = 0, max(4, count * 3), None, False
    for target_index in order:
        if len(questions) >= count or calls >= max_calls:
            break
        previous = [*excluded, *(q['question'] for q in questions)]
        feedback = None
        for attempt in (1, 2):
            if calls >= max_calls:
                break
            calls += 1
            try:
                question, evidence_index = generate_grounded_question(bounded, name, source, difficulty,
                    previous, used_evidence, target_index, attempt, feedback)
                localized = question
                if language == 'en':
                    if not bounded.lock.acquire(timeout=10):
                        raise ChatFailure('Model đang bận. Vui lòng thử lại.', 503)
                    try:
                        quote = question['evidenceQuote']
                        guidance = question_guidance(name, quote)
                        topic = guidance['topic'] if guidance['answer'] else None
                        stem = ENGLISH_STEMS.get(topic)
                        if topic == 'shape' and quote.lower().startswith('miệng'):
                            stem = 'How is the mouth of the object shaped?'
                        localized = english_question(bounded, question, previous, question_stem=stem)
                    finally:
                        bounded.lock.release()
                guard.accept(question)
                questions.append(localized)
                used_evidence.append(evidence_index)
                break
            except ChatFailure as error:
                last_error = error
                logging.getLogger(__name__).warning('Quiz candidate rejected: passage=%d attempt=%d code=%s',
                    target_index, attempt, getattr(error, 'code', error.status))
                if error.status != 502:
                    fatal = True
                    break
                feedback = {'code': getattr(error, 'code', 'invalid_draft'), 'message': str(error)}
        if fatal:
            break
    if not questions and last_error:
        raise last_error
    complete = len(questions) == count
    if not complete:
        if last_error:
            warnings.append(str(last_error))
        if len(order) < count:
            warnings.append('Chưa đủ đoạn tư liệu khác nhau để phân bổ mỗi câu một dữ kiện; hãy bổ sung nguồn.')
        warnings.insert(0, f'Mới tạo {len(questions)}/{count} câu hợp lệ. Bộ câu hỏi chưa hoàn tất; cần kiểm tra và tạo tiếp.')
    return {'requestedCount': count, 'generatedCount': len(questions), 'complete': complete,
        'isDraft': True, 'reviewRequired': True, 'distinctEvidenceCount':len(set(used_evidence)),
        'questions': questions, 'warnings': warnings}
