"""
Base classes to use for building each step in a multi-step process towards a goal.
"""

# --- PRODUCTS ---

# Products:
from .types import Products

# Basic Products types:
from .types import DataFileDescription, DataFileDescriptions

# --- RUNNING MULTI-STEP PROCESS ---

# Base class for running multiple steps while accumulating Products towards a goal:
from .base_steps_runner import BaseStepsRunner

# In each step, we can use the Products from the previous step and choose
# from one of the base-classes below to create new Products.

# --- REQUESTING PRODUCTS FROM USER ---

# Base classes for requesting the user for products:
from .request_products_from_user import DirectorProductGPT


# --- REQUESTS PRODUCTS FROM CHATGPT ---

# Requesting un-structured text:
from .base_products_conversers import BaseProductsGPT

# Requesting un-structured text as part of a gpt-gpt review process:
from .base_products_conversers import BaseProductsReviewGPT

# Requesting quote-enclosed text (with optional gpt-review):
from .request_quoted_test import BaseProductsQuotedReviewGPT

# Requesting LaTeX formatted text (with optional gpt-review):
from .request_latex import BaseLatexProductsReviewGPT

# Requesting Python values (with optional gpt-review):
from .request_python_value import BasePythonValueProductsReviewGPT

# Requesting code (with automatic debugging feedback):
from .request_code import BaseCodeProductsGPT


# --- CONVERTING PRODUCTS TO FILES ---

# Base classes for creating files from Products:
from .base_products_to_file import BaseFileProducer

# Base classes for creating PDFs from LaTeX Products:
from .latex_products_to_pdf import BaseLatexToPDF, BaseLatexToPDFWithAppendix
