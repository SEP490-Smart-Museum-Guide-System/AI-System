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
NARRATION_MODEL_ID = 'onnx-community/Qwen3-4B-Instruct-2507-ONNX'
NARRATION_REVISION = '2bdfea4417ee390519508a6bc7dfbc36f3572981'


class CpuStudio:
    def __init__(self, loader=None):
        self._loader = loader or self._load
        self._narration_loader = loader or self._load_narration
        self._engine = None
        self._narration_engine = None
        self._slot = threading.Lock()

    @staticmethod
    def _load():
        return CpuStudio._load_model(MODEL_ID, REVISION)

    @staticmethod
    def _load_narration():
        return CpuStudio._load_model(NARRATION_MODEL_ID, NARRATION_REVISION, prose=True)

    @staticmethod
    def _load_model(model_id, revision, prose=False):
        path = snapshot_download(model_id, revision=revision, token=False,
            allow_patterns=['onnx/model_q4.onnx*', 'config.json', 'generation_config.json',
                            'tokenizer.json', 'tokenizer_config.json'])
        engine = OnnxChat(path, threads=2, max_input_tokens=2048, max_new_tokens=768, deadline_seconds=170)

        class Adapter:
            lock = engine.lock
            draft_budget_seconds = 170
            def generate_json(self, prompt, validator, **kwargs):
                # Preserve greedy quiz decoding. Narration alone opts into
                # bounded prose sampling/minimum length, matching the GPU path.
                if not prose:
                    kwargs.pop('temperature', None)
                    kwargs.pop('seed', None)
                    kwargs.pop('repetition_penalty', None)
                kwargs['deadline_seconds'] = min(kwargs.get('deadline_seconds') or 170, 170)
                return engine.generate_json(prompt, validator, **kwargs)
        return Adapter()

    @property
    def ready(self):
        return self._engine is not None or self._narration_engine is not None

    def generate(self, body, count=None):
        if not self._slot.acquire(blocking=False):
            raise ChatFailure('Model CPU đang bận. Vui lòng chờ lượt đang chạy hoàn tất.', 503)
        try:
            attribute = '_narration_engine' if body.mode == 'narration' else '_engine'
            engine = getattr(self, attribute)
            if engine is None:
                LOGGER.warning('Loading pinned CPU studio model; no GPU quota is used')
                try:
                    engine = (self._narration_loader if body.mode == 'narration' else self._loader)()
                    setattr(self, attribute, engine)
                except Exception as error:
                    LOGGER.error('CPU model initialization failed type=%s', type(error).__name__)
                    raise ChatFailure('Model CPU chưa tải xong. Vui lòng thử lại sau.', 503) from error
            if body.mode == 'narration':
                return generate_draft(engine, body)
            result = generate_quiz_set(engine, body.artifactName, body.sourceText, body.difficulty,
                                       body.excludeQuestions, count or 1, language=getattr(body, 'languageCode', 'vi'), budget_seconds=170)
            if count is not None:
                return result
            if result.get('generatedCount') != 1 or not result.get('complete'):
                raise ChatFailure('Model chưa tạo được một câu hỏi hợp lệ.', 502)
            return result['questions'][0]
        finally:
            self._slot.release()
