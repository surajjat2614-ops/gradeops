from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor, BitsAndBytesConfig
from qwen_vl_utils import process_vision_info
import torch

# Lazy loading - model loads only when needed
_model = None
_processor = None

def _get_model():
    global _model
    if _model is None:
        model_id = "Qwen/Qwen2.5-VL-3B-Instruct"
        quant_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )
        print("Loading Qwen2.5-VL model (first time only)...")
        _model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            model_id,
            quantization_config=quant_config,
            device_map="auto"
        )
        _model.eval()
    return _model

def _get_processor():
    global _processor
    if _processor is None:
        model_id = "Qwen/Qwen2.5-VL-3B-Instruct"
        _processor = AutoProcessor.from_pretrained(model_id, max_pixels=512*28*28)
    return _processor

# Backward compatible imports - lazy proxies
class _LazyProxy:
    def __init__(self, getter):
        self._getter = getter
    def __getattr__(self, name):
        return getattr(self._getter(), name)
    def __call__(self, *args, **kwargs):
        return self._getter()(*args, **kwargs)

model = _LazyProxy(_get_model)
processor = _LazyProxy(_get_processor)



def transcribe_snippet(image_path, context_text=None, max_tokens=256):
    # Lazy load model only when first called
    model = _get_model()
    processor = _get_processor()

    context_section = (
        f"\nQUESTION CONTEXT: {context_text}\nUse this context to help resolve ambiguous handwriting or specific terminology related to the question."
        if context_text else ""
    )

    PROMPT = (
        "Literal transcription only. Return ONLY the text visible in the image. "
        "Strictly NO definitions, NO explanations, NO external knowledge. "
        "If unclear, use [?]. Preserve LaTeX math and line breaks."
        f"{context_section}"
    )

    if not image_path.startswith("file://"):
        image_path = f"file://{image_path}"


    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image_path},
                {"type": "text",  "text": PROMPT},
            ],
        }
    ]


    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, _ = process_vision_info(messages)


    inputs = processor(
        text=[text],
        images=image_inputs,
        padding=True,
        return_tensors="pt"
    ).to(model.device)


    with torch.no_grad():
        generated_ids = model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            do_sample=False,
            use_cache=True,
        )

    generated_ids_trimmed = [
        out_ids[len(in_ids):]
        for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
    ]

    output_text = processor.batch_decode(
        generated_ids_trimmed,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False  # Preserves LaTeX spacing
    )

    return output_text[0].strip()


if __name__ == "__main__":
    result = transcribe_snippet("C:/Users/hrima/gradeops-vision/data/snippets/page_0_question_2.png")
    print(result)