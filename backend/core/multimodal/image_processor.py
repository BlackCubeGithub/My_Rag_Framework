"""
Image Processor
Handles image understanding and VQA
"""
import structlog
from typing import Optional
from dataclasses import dataclass
import base64
from pathlib import Path

logger = structlog.get_logger()


@dataclass
class ImageResult:
    """Result of image processing"""
    image_id: str
    caption: str
    description: str
    extracted_text: str
    vqa_answers: dict


class ImageProcessor:
    """
    Processes images for multimodal RAG.

    Capabilities:
    - Image captioning
    - OCR text extraction
    - Visual Question Answering (VQA)
    - Image description generation
    """

    def __init__(
        self,
        caption_model: str = "Salesforce/blip-image-captioning-base",
        vqa_model: str = "Salesforce/blip-vqa-base",
    ):
        self.caption_model = caption_model
        self.vqa_model = vqa_model
        self._captioner = None
        self._vqa_model = None

    def _load_captioner(self):
        """Lazy load captioning model"""
        if self._captioner is None:
            try:
                from transformers import BlipProcessor, BlipForConditionalGeneration
                from PIL import Image

                self._captioner = {
                    "processor": BlipProcessor.from_pretrained(self.caption_model),
                    "model": BlipForConditionalGeneration.from_pretrained(self.caption_model),
                }
                logger.info("caption_model_loaded")

            except ImportError:
                logger.warning("transformers not available, using mock captioning")
                self._captioner = "mock"

    async def process_image(
        self,
        image_path: str,
        extract_text: bool = True,
    ) -> ImageResult:
        """
        Process a single image.

        Args:
            image_path: Path to image file
            extract_text: Whether to extract text via OCR

        Returns:
            ImageResult with caption, description, and extracted text
        """
        logger.info("processing_image", path=image_path)

        caption = await self._generate_caption(image_path)
        description = await self._generate_description(image_path)

        extracted_text = ""
        if extract_text:
            extracted_text = await self._extract_text(image_path)

        return ImageResult(
            image_id=Path(image_path).stem,
            caption=caption,
            description=description,
            extracted_text=extracted_text,
            vqa_answers={},
        )

    async def _generate_caption(self, image_path: str) -> str:
        """Generate image caption"""
        self._load_captioner()

        if self._captioner == "mock":
            return f"Image: {Path(image_path).name}"

        try:
            from PIL import Image
            import torch

            image = Image.open(image_path).convert("RGB")

            inputs = self._captioner["processor"](image, return_tensors="pt")

            with torch.no_grad():
                output = self._captioner["model"].generate(**inputs)

            caption = self._captioner["processor"].decode(output[0], skip_special_tokens=True)
            return caption

        except Exception as e:
            logger.error("caption_generation_failed", error=str(e))
            return f"Image: {Path(image_path).name}"

    async def _generate_description(self, image_path: str) -> str:
        """Generate detailed image description"""
        self._load_captioner()

        if self._captioner == "mock":
            return f"Description of {Path(image_path).name}"

        try:
            from PIL import Image
            import torch

            image = Image.open(image_path).convert("RGB")

            prompt = "a detailed description of this image:"
            inputs = self._captioner["processor"](
                image, prompt, return_tensors="pt"
            )

            with torch.no_grad():
                output = self._captioner["model"].generate(**inputs)

            description = self._captioner["processor"].decode(output[0], skip_special_tokens=True)
            return description

        except Exception as e:
            logger.error("description_generation_failed", error=str(e))
            return ""

    async def _extract_text(self, image_path: str) -> str:
        """Extract text from image using OCR"""
        try:
            import pytesseract
            from PIL import Image

            image = Image.open(image_path)
            text = pytesseract.image_to_string(image, lang="chi_sim+eng")

            logger.info("ocr_completed", text_length=len(text))
            return text.strip()

        except ImportError:
            logger.warning("pytesseract not available, using PaddleOCR")
            return await self._extract_text_paddle(image_path)
        except Exception as e:
            logger.error("ocr_failed", error=str(e))
            return ""

    async def _extract_text_paddle(self, image_path: str) -> str:
        """Extract text using PaddleOCR"""
        try:
            from paddleocr import PaddleOCR

            ocr = PaddleOCR(use_angle_cls=True, lang="ch")
            result = ocr.ocr(image_path, cls=True)

            texts = []
            if result and result[0]:
                for line in result[0]:
                    if line and len(line) >= 2:
                        texts.append(line[1][0])

            return "\n".join(texts)

        except ImportError:
            logger.warning("PaddleOCR not available")
            return ""
        except Exception as e:
            logger.error("paddle_ocr_failed", error=str(e))
            return ""

    async def vqa(
        self,
        image_path: str,
        questions: list[str],
    ) -> dict[str, str]:
        """
        Visual Question Answering on image.

        Args:
            image_path: Path to image
            questions: List of questions about the image

        Returns:
            Dictionary mapping questions to answers
        """
        logger.info("vqa_started", questions_count=len(questions))

        answers = {}

        for question in questions:
            answer = await self._ask_question(image_path, question)
            answers[question] = answer

        return answers

    async def _ask_question(self, image_path: str, question: str) -> str:
        """Ask a single question about an image"""
        self._load_captioner()

        if self._captioner == "mock":
            return "Answer based on image analysis"

        try:
            from PIL import Image
            import torch
            from transformers import BlipForQuestionAnswering, BlipProcessor

            qa_model_name = "Salesforce/blip-vqa-base"
            processor = BlipProcessor.from_pretrained(qa_model_name)
            model = BlipForQuestionAnswering.from_pretrained(qa_model_name)

            image = Image.open(image_path).convert("RGB")
            inputs = processor(image, question, return_tensors="pt")

            with torch.no_grad():
                output = model.generate(**inputs)

            answer = processor.decode(output[0], skip_special_tokens=True)
            return answer

        except Exception as e:
            logger.error("vqa_failed", error=str(e))
            return "Unable to answer"

    async def batch_process(
        self,
        image_paths: list[str],
    ) -> list[ImageResult]:
        """Process multiple images"""
        import asyncio

        tasks = [self.process_image(path) for path in image_paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("batch_process_failed", index=i, error=str(result))
            else:
                processed.append(result)

        return processed
