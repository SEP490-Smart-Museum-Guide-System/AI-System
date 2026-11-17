"""Compose a bounded quiz set inside one GPU allocation, using SMGS validators."""
import time
from app.engine import ChatFailure
from app.studio import norm
from grounded_quiz import generate_grounded_question


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


def generate_quiz_set(engine, name, source, difficulty, excluded, count=5, *, budget_seconds=85, clock=time.monotonic):
    if type(count) is not int or count not in (1, 3, 5):
        raise ValueError('Chọn bộ 1, 3 hoặc 5 câu hỏi.')
    bounded = DeadlineEngine(engine, clock() + budget_seconds, clock)
    questions, warnings, used_evidence = [], [], []
    for _ in range(count):
        previous = [*excluded, *(q['question'] for q in questions)]
        try:
            for attempt in (1, 2):
                try:
                    question, evidence_index = generate_grounded_question(bounded, name, source, difficulty,
                        previous, used_evidence, attempt)
                    if norm(question['question']) in {norm(q) for q in previous}:
                        raise ChatFailure('AI trả câu hỏi trùng với câu đã tạo.', 502)
                    break
                except ChatFailure as error:
                    if attempt == 2 or error.status != 502:
                        raise
            questions.append(question)
            used_evidence.append(evidence_index)
        except ChatFailure as error:
            if not questions:
                raise
            warnings.append(str(error))
            break
    complete = len(questions) == count
    if not complete:
        warnings.insert(0, f'Mới tạo {len(questions)}/{count} câu hợp lệ. Bộ câu hỏi chưa hoàn tất; cần kiểm tra và tạo tiếp.')
    return {'requestedCount': count, 'generatedCount': len(questions), 'complete': complete,
        'isDraft': True, 'questions': questions, 'warnings': warnings}
