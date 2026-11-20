"""Bounded ONNX CPU inference on the existing Space when ZeroGPU quota is gone."""
import logging
import threading

from huggingface_hub import snapshot_download

from app.engine import ChatFailure, OnnxChat
from app.studio import generate_draft
from quiz_set import generate_quiz_set

LOGGER = logging.getLogger(__name__)
MODEL_ID = 'onnx-community/Qwen2.5-1.5B-Instruct'
REVISION = 'd54957e3af1be04546436e874a60fe386041b244'


class CpuStudio:
    def __init__(self, loader=None):
        self._loader = loader or self._load
        self._engine = None
        self._slot = threading.Lock()

    @staticmethod
    def _load():
        path = snapshot_download(MODEL_ID, revision=REVISION, token=False,
            allow_patterns=['onnx/model_q4.onnx', 'config.json', 'generation_config.json',
                            'tokenizer.json', 'tokenizer_config.json'])
        engine = OnnxChat(path, threads=2, max_input_tokens=2048, max_new_tokens=768, deadline_seconds=170)

        class Adapter:
            lock = engine.lock
            def generate_json(self, prompt, validator, **kwargs):
                # ONNX decoder is deterministic. A rejected candidate is retried
                # only with the original pipeline's explicit correction prompt.
                kwargs.pop('temperature', None)
                kwargs.pop('seed', None)
                kwargs['deadline_seconds'] = min(kwargs.get('deadline_seconds') or 170, 170)
                return engine.generate_json(prompt, validator, **kwargs)
        return Adapter()

    @property
    def ready(self):
        return self._engine is not None

    def generate(self, body, count=None):
        if not self._slot.acquire(blocking=False):
            raise ChatFailure('Model CPU đang bận. Vui lòng chờ lượt đang chạy hoàn tất.', 503)
        try:
            if self._engine is None:
                LOGGER.warning('Loading pinned CPU studio model; no GPU quota is used')
                try:
                    self._engine = self._loader()
                except Exception as error:
                    LOGGER.error('CPU model initialization failed type=%s', type(error).__name__)
                    raise ChatFailure('Model CPU chưa tải xong. Vui lòng thử lại sau.', 503) from error
            if body.mode == 'narration':
                return generate_draft(self._engine, body)
            result = generate_quiz_set(self._engine, body.artifactName, body.sourceText, body.difficulty,
                                       body.excludeQuestions, count or 1, budget_seconds=170)
            if count is not None:
                return result
            if result.get('generatedCount') != 1 or not result.get('complete'):
                raise ChatFailure('Model chưa tạo được một câu hỏi hợp lệ.', 502)
            return result['questions'][0]
        finally:
            self._slot.release()
