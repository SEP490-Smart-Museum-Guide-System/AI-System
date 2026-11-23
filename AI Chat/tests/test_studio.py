import json
import unittest
import threading
from types import SimpleNamespace
from app.engine import ChatFailure
from app.studio import english_narration, english_question, generate_draft, validate_draft, narration_quality, narration_result, narration_source


class DraftTests(unittest.TestCase):
    source = 'Máy nén khí có công suất 7,5hp, do Xí nghiệp thiết bị lạnh sản xuất.'
    def quiz(self):
        return {'question': 'Máy nén khí có công suất bao nhiêu?', 'options': ['7,5hp', '10hp', '20hp', '30hp'],
                'correctIndex': 0, 'explanation': 'Nhãn ghi công suất 7,5hp.', 'evidenceQuote': self.source}

    def test_english_quiz_preserves_source_and_answer_slot(self):
        draft = self.quiz()
        fields = {'question': 'What is the rated power?', 'option0': '7.5hp', 'option1': '10hp',
                  'option2': '20hp', 'option3': '30hp', 'explanation': 'The label states 7.5hp.'}
        engine = SimpleNamespace(generate_json=lambda prompt, validate, **kwargs: validate(json.dumps(fields)))
        result = english_question(engine, draft, [])
        self.assertEqual(result['evidenceQuote'], self.source)
        self.assertEqual(result['options'][result['correctIndex']], '7.5hp')
        with self.assertRaises(ChatFailure):
            english_question(engine, draft, [result['question']])

    def test_english_narration_keeps_uncertainty_and_verbatim_evidence(self):
        source = 'Chất liệu có thể là đất nung.'
        fields = {'title': 'The Jar', 'passage0': 'The jar may be made of fired clay.'}
        engine = SimpleNamespace(generate_json=lambda prompt, validate, **kwargs: validate(json.dumps(fields)))
        request = SimpleNamespace(artifactName='Hũ', audience='general', tone='vivid')
        self.assertEqual(english_narration(engine, request, source)['evidenceQuotes'], [source])
        fields['passage0'] = 'The jar is made of fired clay.'
        with self.assertRaises(ChatFailure):
            english_narration(engine, request, source)

    def test_valid_draft_and_unique_correct_option(self):
        value = self.quiz()
        self.assertEqual(validate_draft(json.dumps(value), self.source, 'quiz', [])['correctIndex'], 0)

    def test_invalid_or_unsupported_quiz_is_rejected(self):
        for mutation in [{'correctIndex': 4}, {'correctIndex': True}, {'options': ['A', 'A']},
                         {'evidenceQuote': 'Đây là hiện vật năm 1900'}, {'explanation': 'Sản xuất năm 1900.'},
                         {'options': ['45hp', '10hp', '20hp', '30hp']}, {'id': 1}]:
            with self.assertRaises(ChatFailure): validate_draft(json.dumps({**self.quiz(), **mutation}), self.source, 'quiz', [])

    def test_repeated_questions_are_not_counted_as_new(self):
        with self.assertRaises(ChatFailure): validate_draft(json.dumps(self.quiz()), self.source, 'quiz', [self.quiz()['question']])

    def test_correct_option_is_resolved_from_source_not_model_index(self):
        value = self.quiz(); value['correctIndex'] = 1
        self.assertEqual(validate_draft(json.dumps(value), self.source, 'quiz', [])['correctIndex'], 0)

    def test_narration_needs_real_evidence_and_cannot_invent_years(self):
        value = {'title': 'Máy nén khí', 'narrationText': self.source, 'evidenceQuotes': [self.source]}
        self.assertEqual(validate_draft(json.dumps(value), self.source, 'narration', []), value)
        for changed in [{'evidenceQuotes': []}, {'narrationText': self.source + ' Thiết bị có từ năm 1900.'}, {'status': 'published'}]:
            with self.assertRaises(ChatFailure): validate_draft(json.dumps({**value, **changed}), self.source, 'narration', [])

    def test_question_answer_consistency_requires_independent_grounded_answer(self):
        class Engine:
            def __init__(self, verification): self.lock = threading.Lock(); self.calls = 0; self.verification = verification
            def generate_json(inner, prompt, validator, **options):
                inner.calls += 1
                return validator(json.dumps(self.quiz() if inner.calls == 1 else inner.verification))
        request = SimpleNamespace(sourceText=self.source, mode='quiz', audience='general', tone='vivid', difficulty='easy',
                                  artifactId=17, artifactName='Máy nén khí', excludeQuestions=[])
        engine = Engine({'answer': '7,5hp', 'supported': True})
        self.assertEqual(generate_draft(engine, request)['correctIndex'], 0)
        engine = Engine({'answer': 'Xí nghiệp thiết bị lạnh', 'supported': True})
        with self.assertRaises(ChatFailure): generate_draft(engine, request)
        self.assertFalse(engine.lock.locked())

    def test_narration_rewrites_instead_of_accepting_copied_notes(self):
        source = 'Miệng bình loe rộng. ' * 25
        for text, code in [(source, 'narration_copied_source'), ('Miệng bình loe rộng.', 'narration_too_short'),
                           ('Chất liệu: chưa rõ. Hình dáng: miệng loe. ' + 'Mời quan sát hiện vật. ' * 25, 'narration_still_notes')]:
            with self.subTest(code=code), self.assertRaises(ChatFailure) as caught:
                narration_quality({'narrationText': text}, source)
            self.assertEqual(caught.exception.code, code)

    def test_rejected_copy_is_retried_once_with_correction_and_lock_released(self):
        source = 'Bình gốm được dùng để đựng nước.'
        # Labelled model fixture: tests retry/validation, not model writing quality.
        rewritten = ('Mời quý khách dừng lại trước chiếc bình và cùng tìm hiểu thông tin về công dụng của hiện vật. '
                     'Theo tư liệu, đây là một chiếc bình gốm dùng để chứa nước. '
                     'Hãy dành một chút thời gian quan sát hiện vật trước khi tiếp tục hành trình tham quan. '
                     'Khi nhìn lại chiếc bình, quý khách hãy ghi nhớ công dụng đựng nước được giới thiệu trong tư liệu.')
        class Engine:
            draft_budget_seconds = 30
            def __init__(self, always_copy=False):
                self.lock = threading.Lock(); self.calls = []; self.always_copy = always_copy
            def generate_json(inner, prompt, validator, **options):
                inner.calls.append((prompt, options))
                text = source if inner.always_copy or len(inner.calls) == 1 else rewritten
                return validator(text)
        request = SimpleNamespace(sourceText=source, mode='narration', audience='general', tone='vivid',
                                  artifactName='Bình gốm', excludeQuestions=[])
        engine = Engine()
        self.assertEqual(generate_draft(engine, request)['narrationText'], rewritten)
        self.assertEqual(len(engine.calls), 2)
        self.assertIn('Revise the narration', engine.calls[1][0])
        self.assertLessEqual(engine.calls[1][1]['deadline_seconds'], engine.calls[0][1]['deadline_seconds'])
        self.assertFalse(engine.lock.locked())
        engine = Engine(always_copy=True)
        with self.assertRaises(ChatFailure): generate_draft(engine, request)
        self.assertEqual(len(engine.calls), 2)
        self.assertFalse(engine.lock.locked())

    def test_narration_metadata_uses_only_literal_source_spans(self):
        source = 'Miệng bình loe rộng. ' * 25
        prose = ('Mời quý khách quan sát hiện vật ở trước mặt. ' + 'Hãy nhìn kỹ phần miệng bình đang loe rộng. ' * 12)
        result = narration_result(prose, source, 'Bình gốm')
        self.assertEqual(result['title'], 'Bình gốm')
        self.assertEqual(result['narrationText'], prose.strip())
        self.assertEqual(result['evidenceQuotes'], ['Miệng bình loe rộng.'])
        with self.assertRaises(ChatFailure): narration_result(prose + ' Năm 1900.', source, 'Bình gốm')
        with self.assertRaises(ChatFailure): narration_result('{"narrationText":"notes"}', source, 'Bình gốm')

    def test_software_metadata_is_not_spoken_but_uncertain_facts_are_preserved(self):
        facts = 'Chất liệu có lẽ là đất nung. Công dụng có thể là đựng nước.'
        cleaned = narration_source(facts + ' Đây là tư liệu giả lập để kiểm thử phần mềm.')
        self.assertIn('có lẽ', cleaned)
        self.assertIn('có thể', cleaned)
        self.assertNotIn('phần mềm', cleaned)
        with self.assertRaises(ChatFailure): narration_source('Đây là tư liệu giả lập để kiểm thử phần mềm.')
