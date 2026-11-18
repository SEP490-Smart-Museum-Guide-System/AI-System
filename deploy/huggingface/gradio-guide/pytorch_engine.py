"""HF-only PyTorch adapter. Reuse the original extractive prompt and source guard."""
import json
import os
import threading

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, StoppingCriteria, StoppingCriteriaList

from app.engine import ChatFailure, ground_answer, make_prompt, parse_answer

MODEL_ID = 'Qwen/Qwen2.5-1.5B-Instruct'
REVISION = '989aa7980e4cf806f80c7fef2b1adb7bc71aa306'


class JsonComplete(StoppingCriteria):
    def __init__(self, tokenizer, prompt_length):
        self.tokenizer, self.prompt_length = tokenizer, prompt_length

    def __call__(self, input_ids, scores, **kwargs):
        text = self.tokenizer.decode(input_ids[0, self.prompt_length:], skip_special_tokens=True).strip()
        try:
            value = json.loads(text)
        except ValueError:
            return False
        return isinstance(value, dict)


class TorchGuideEngine:
    def __init__(self):
        self.device = os.environ.get('SMGS_DEVICE', 'cuda' if os.environ.get('SPACE_ID') else 'cpu')
        if self.device not in {'cuda', 'cpu'}:
            raise ValueError('Unsupported SMGS_DEVICE')
        torch.set_num_threads(2)
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=REVISION, trust_remote_code=False)
        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID, revision=REVISION, trust_remote_code=False,
            dtype=torch.float16 if self.device == 'cuda' else torch.bfloat16,
        ).to(self.device).eval()
        self.lock = threading.Lock()
        self.deadline_seconds = 45

    def answer(self, context, question, history):
        if not self.lock.acquire(timeout=0.5):
            raise ChatFailure('Trợ lý đang xử lý câu hỏi khác. Vui lòng thử lại.', 503)
        try:
            inputs = self.tokenizer(make_prompt(context, question, history), return_tensors='pt', add_special_tokens=False)
            length = inputs['input_ids'].shape[1]
            if length > 2048:
                raise ChatFailure('Nội dung hoặc hội thoại quá dài. Hãy chọn tư liệu ngắn hơn.', 422)
            inputs = {key: value.to(self.device) for key, value in inputs.items()}
            with torch.inference_mode():
                output = self.model.generate(
                    **inputs, do_sample=False, max_new_tokens=384, max_time=self.deadline_seconds,
                    pad_token_id=self.tokenizer.eos_token_id,
                    stopping_criteria=StoppingCriteriaList([JsonComplete(self.tokenizer, length)]),
                )
            text = self.tokenizer.decode(output[0, length:], skip_special_tokens=True).strip()
            return ground_answer(parse_answer(text), context)
        finally:
            self.lock.release()
