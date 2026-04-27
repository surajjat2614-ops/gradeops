from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info
import torch


model_id = "Qwen/Qwen2.5-VL-3B-Instruct"
model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
    model_id, torch_dtype=torch.bfloat16, device_map="auto"
)
model.eval()  # Read-only mode


processor = AutoProcessor.from_pretrained(model_id, max_pixels=512*28*28)



def transcribe_snippet(image_path):

    PROMPT = (
        "Transcribe all text in this image exactly as written. "
        "Use LaTeX notation for any mathematical expressions, "
        "subscripts, superscripts, fractions, or symbols. "
        "Wrap inline math in $...$ and block equations in $$...$$. "
        "If a word is unclear, make your best guess and mark it with [?]. "
        "Preserve all line breaks and formatting as they appear in the image."
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
            max_new_tokens=256,   
            do_sample=False,      
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