"""Validate the deployed REST schema without loading GPU models."""
import ast
from pathlib import Path
import unittest
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

ROOT = Path(__file__).resolve().parents[3]


def schema(path, names):
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in names]
    scope = dict(BaseModel=BaseModel, ConfigDict=ConfigDict, Field=Field, Literal=Literal,
                 model_validator=model_validator)
    exec(compile(ast.Module(body=classes, type_ignores=[]), str(path), 'exec'), scope)
    return scope


class StudioContractTests(unittest.TestCase):
    payload = dict(artifactId=11, artifactName='Ngói uyên ương',
                   sourceText='Ngói được làm bằng đất nung, trang trí hình uyên ương.')

    def test_backend_single_count_is_accepted_for_both_modes(self):
        for path, name in [(ROOT/'AI Chat/app/main.py', 'DraftRequest'),
                           (ROOT/'deploy/huggingface/gradio-quiz/app.py', 'QuizPayload')]:
            model = schema(path, {name})[name]
            for mode in ('quiz', 'narration'):
                for count in ({}, {'count': 1}):
                    with self.subTest(model=name, mode=mode, count=count):
                        self.assertEqual(model.model_validate({**self.payload, 'mode': mode, **count}).count, 1)
                for extra in ({'count': 3}, {'unexpected': True}):
                    with self.assertRaises(ValidationError):
                        model.model_validate({**self.payload, 'mode': mode, **extra})

    def test_batch_contract_still_accepts_only_supported_sizes(self):
        models = schema(ROOT/'deploy/huggingface/gradio-quiz/app.py', {'QuizPayload', 'QuizSetPayload'})
        for count in (1, 3, 5):
            self.assertEqual(models['QuizSetPayload'].model_validate({**self.payload, 'count': count}).count, count)
        with self.assertRaises(ValidationError):
            models['QuizSetPayload'].model_validate({**self.payload, 'count': 2})
