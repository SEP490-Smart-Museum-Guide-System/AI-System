"""Space-only Qwen adapter; local SMGS ONNX services are unchanged."""
import json
import os
import threading
import logging
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, StoppingCriteria, StoppingCriteriaList
from app.engine import ChatFailure

MODEL_ID = 'Qwen/Qwen2.5-1.5B-Instruct'
REVISION = '989aa7980e4cf806f80c7fef2b1adb7bc71aa306'
NARRATION_MODEL_ID = 'Qwen/Qwen3-4B-Instruct-2507'
NARRATION_REVISION = 'cdbee75f17c01a7cc42f958dc650907174af0554'
LOGGER = logging.getLogger(__name__)


class JsonComplete(StoppingCriteria):
    def __init__(self, tokenizer, prompt_length, prefix):
        self.tokenizer, self.prompt_length, self.prefix = tokenizer, prompt_length, prefix

    def __call__(self, input_ids, scores, **kwargs):
        text = self.prefix + self.tokenizer.decode(input_ids[0, self.prompt_length:], skip_special_tokens=True).strip()
        try:
            return isinstance(json.loads(text), dict)
        except ValueError:
            return False


class TorchQuizEngine:
    draft_budget_seconds = 40
    def __init__(self, model_id=MODEL_ID, revision=REVISION):
        self.device = os.environ.get('SMGS_DEVICE', 'cuda' if os.environ.get('SPACE_ID') else 'cpu')
        if self.device not in {'cuda', 'cpu'}: raise ValueError('Unsupported SMGS_DEVICE')
        torch.set_num_threads(2)
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision, trust_remote_code=False)
        self.model = AutoModelForCausalLM.from_pretrained(model_id, revision=revision, trust_remote_code=False,
            dtype=torch.float16 if self.device == 'cuda' else torch.float32).to(self.device).eval()
        self.lock = threading.Lock()

    def generate_json(self, prompt, validator, *, max_new_tokens=None, prefix='', deadline_seconds=None,
            temperature=0.0, seed=None, min_new_tokens=0, repetition_penalty=1):
        inputs = self.tokenizer(prompt, return_tensors='pt', add_special_tokens=False)
        length = inputs['input_ids'].shape[1]
        # The model supports a much larger context than the old 2k hard cap.
        # Keep a conservative 4k budget so ordinary approved artifact records fit
        # without turning long, multi-question prompts into slow GPU/CPU requests.
        if length > 4096: raise ChatFailure('Tư liệu và chỉ dẫn vượt giới hạn 4.096 token. Hãy rút gọn tư liệu hoặc câu hỏi đã có.', 422)
        inputs = {name: value.to(self.device) for name, value in inputs.items()}
        sampling = temperature > 0
        devices = [torch.cuda.current_device()] if self.device == 'cuda' else []
        with torch.inference_mode(), torch.random.fork_rng(devices=devices):
            if seed is not None: torch.manual_seed(seed)
            output = self.model.generate(**inputs, do_sample=sampling,
                temperature=temperature if sampling else None, top_p=0.9 if sampling else None,
                top_k=40 if sampling else None, max_new_tokens=min(max_new_tokens or 350, 1280),
                min_new_tokens=min(min_new_tokens, min(max_new_tokens or 350, 1280)),
                repetition_penalty=repetition_penalty,
                max_time=min(deadline_seconds or 40, 40), pad_token_id=self.tokenizer.eos_token_id,
                stopping_criteria=StoppingCriteriaList([JsonComplete(self.tokenizer, length, prefix)]))
        text = prefix + self.tokenizer.decode(output[0, length:], skip_special_tokens=True).strip()
        # The shared SMGS validator rejects incomplete JSON, fabricated numbers and unsupported answers.
        try:
            return validator(text)
        except ChatFailure as error:
            generated = output.shape[1] - length
            code = getattr(error, 'code', 'invalid_draft')
            if code == 'invalid_json' and generated >= min(max_new_tokens or 350, 1280):
                code = 'output_token_limit'
                error.code = code
            LOGGER.warning('Draft rejected code=%s generatedTokens=%d outputChars=%d', code, generated, len(text))
            raise
