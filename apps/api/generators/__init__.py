from schemas.context import ContentType

from .base import BaseGenerator
from .compare_table import CompareTableGenerator
from .exam_review import ExamReviewGenerator
from .formula_dict import FormulaDictGenerator
from .mnemonic import MnemonicGenerator
from .summary_pages import SummaryPagesGenerator
from .tri_color import TriColorGenerator


def get_generator(content_type: ContentType) -> BaseGenerator:
    registry: dict[str, BaseGenerator] = {
        "mnemonic": MnemonicGenerator(),
        "tri_color": TriColorGenerator(),
        "summary_pages": SummaryPagesGenerator(),
        "formula_dict": FormulaDictGenerator(),
        "compare_table": CompareTableGenerator(),
        "exam_review": ExamReviewGenerator(),
    }
    return registry[content_type]

