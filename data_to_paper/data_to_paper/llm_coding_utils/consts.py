# ALLOWED_PLOT_KINDS = ['line', 'scatter', 'bar', 'hist', 'box', 'kde', 'hexbin', 'pie']
import numbers
from typing import Union

from data_to_paper.utils.mutable import Mutable

FIG_SIZE_INCHES = (7.5, 2.5)
FIG_DPI = Mutable(400)

ALLOWED_PLOT_KINDS = ['bar']  # TODO: Add support for more plot kinds

DF_ALLOWED_VALUE_TYPES = (numbers.Number, str, bool, tuple)
DF_ALLOWED_COLUMN_TYPES = (numbers.Number, str, bool)
DfColumnTyping = Union[numbers.Number, str, bool]  # not tuple because we need tuple to choose a pair of columns
