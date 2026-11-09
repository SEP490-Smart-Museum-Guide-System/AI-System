import json
import unittest
import threading
from types import SimpleNamespace
from app.engine import ChatFailure
from app.studio import generate_draft, validate_draft


class DraftTests(unittest.TestCase):
    source = 'Máy nén khí có công suất 7,5hp, do Xí nghiệp thiết bị lạnh sản xuất.'
    def quiz(self):
        return {'question': 'Máy nén khí có công suất bao nhiêu?', 'options': ['7,5hp', '10hp', '20hp', '30hp'],
                'correctIndex': 0, 'explanation': 'Nhãn ghi công suất 7,5hp.', 'evidenceQuote': self.source}

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
