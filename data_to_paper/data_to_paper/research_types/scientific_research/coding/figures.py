from dataclasses import dataclass
from typing import Type, Tuple, Optional, Collection

from data_to_paper.base_steps import DebuggerConverser
from data_to_paper.base_steps.request_code import CodeReviewPrompt
from data_to_paper.code_and_output_files.code_and_output import CodeAndOutput
from data_to_paper.code_and_output_files.output_file_requirements import TextContentOutputFileRequirement, \
    OutputFileRequirements, OutputFileRequirement
from data_to_paper.research_types.scientific_research.cast import ScientificAgent
from data_to_paper.research_types.scientific_research.coding.base_code_conversers import BaseScientificCodeProductsGPT
from data_to_paper.research_types.scientific_research.coding.latex_table_debugger import UtilsCodeRunner
from data_to_paper.research_types.scientific_research.scientific_products import HypertargetPrefix, ScientificProducts
from data_to_paper.run_gpt_code.code_runner import CodeRunner
from data_to_paper.utils import dedent_triple_quote_str


@dataclass
class CreateFiguresCodeAndOutput(CodeAndOutput):
    def get_code_header_for_file(self, filename: str) -> Optional[str]:
        # 'figure_*.tex' -> '# FIGURE *'
        if filename.startswith('figure_') and filename.endswith('.tex'):
            return f'# FIGURE {filename[7:-4]}'
        return None


@dataclass(frozen=True)
class FigureOutputFileRequirement(OutputFileRequirement):
    filename: str = '*.png'
    minimal_count: int = 1
    should_keep_file: bool = True

    def get_content(self, file_path: str) -> Optional[str]:
        """
        Return html file containing the png and the caption
        """
        return f'<img src="{file_path}" alt="Figure" />'



@dataclass(frozen=True)
class FigureLatexOutputFileRequirement(TextContentOutputFileRequirement):
    filename: str = '*.tex'
    minimal_count: int = 1
    hypertarget_prefixes = HypertargetPrefix.FIGURES.value
    max_tokens = None
    should_keep_file: bool = True


@dataclass
class FigureDebuggerConverser(DebuggerConverser):
    products: ScientificProducts = None
    code_runner_cls: Type[CodeRunner] = UtilsCodeRunner


@dataclass
class CreateFiguresCodeProductsGPT(BaseScientificCodeProductsGPT):
    code_step: str = 'figures'
    debugger_cls: Type[DebuggerConverser] = FigureDebuggerConverser
    code_and_output_cls: Type[CodeAndOutput] = CreateFiguresCodeAndOutput
    headers_required_in_code: Tuple[str, ...] = (
        '# IMPORT',
        '# PREPARATION FOR ALL FIGURES',
    )
    user_agent: ScientificAgent = ScientificAgent.InterpretationReviewer
    background_product_fields: Tuple[str, ...] = \
        ('data_file_descriptions', 'research_goal', 'codes:data_preprocessing', 'codes:data_analysis',
         'created_files_content:data_analysis:table_?.pkl')
    supported_packages: Tuple[str, ...] = ('pandas', 'numpy', 'matplotlib', 'seaborn', 'my_utils')
    output_file_requirements: OutputFileRequirements = OutputFileRequirements(
        [FigureOutputFileRequirement(), FigureLatexOutputFileRequirement()])

    provided_code: str = dedent_triple_quote_str('''
        def to_latex_figure_with_caption(figure, filename: str, caption: str, label: str, comment: str = None):
            """
            Save a figure with a caption and label.
            """
            figure.savefig(filename)
            latex = f"""
                \\begin{{figure}}[htbp]
                \\centering
                \\includegraphics[width=0.8\\textwidth]{{{filename.replace(".png", "")}}}
                \\caption{{{caption}}}
                \\label{{{label}}}
                \\end{{figure}}
            """
            if comment:
                latex = comment + latex
            with open(filename.replace('.png', '.tex'), 'w') as f:
                f.write(latex)
            return latex
        ''')

    mission_prompt: str = dedent_triple_quote_str('''
        Please write a Python code to create figures using the "matplotlib" and "seaborn" packages, and save them as \t
        ".png" files with captions and labels for our scientific paper.

        Your code should use the following custom function provided for import from `my_utils`:
        
        ```python
        def to_latex_figure_with_caption(figure, filename: str, caption: str, label: str, comment: str = None):
            """
            Save a figure with a caption and label.
            """
            figure.savefig(filename)
            latex = f"""
                \\begin{{figure}}[htbp]
                \\centering
                \\includegraphics[width=0.8\\textwidth]{{{filename.replace(".png", "")}}}
                \\caption{{{caption}}}
                \\label{{{label}}}
                \\end{{figure}}
            """
            if comment:
                latex = comment + latex
            with open(filename.replace('.png', '.tex'), 'w') as f:
                f.write(latex)
            return latex
        ```
        
        Your code should:
        
        Use matplotlib and seaborn to create the figures.
        Ensure each figure is saved as a .png file.
        Add a caption and label to each figure using the provided to_latex_figure_with_caption function.
        To ensure clarity and consistency, define a dictionary, figure_details, which maps figure identifiers to \t
        their corresponding captions and labels. This will help avoid any mistakes in labeling and captioning.
        
        Overall, the code must have the following structure:
        
        ```python
        # IMPORT
        import pandas as pd
        import matplotlib.pyplot as plt
        import seaborn as sns
        from my_utils import to_latex_figure_with_caption
        
        pd.read_csv('<data>')
        
        # PREPARATION FOR ALL FIGURES
        figure_details = {
            'fig1': {
                'caption': 'Distribution of variable X',
                'label': 'fig:distribution_x',
            },
            'fig2': {
                'caption': 'Correlation between variables Y and Z',
                'label': 'fig:correlation_y_z',
            },
            # Add more figure details as needed
        }
        
        # FIGURE 1:
        # Create the figure using matplotlib and seaborn
        fig1, ax1 = plt.subplots()
        sns.histplot(data=df, x='variable_x', ax=ax1)
        # Save the figure with caption and label
        to_latex_figure_with_caption(
            fig1, 'figure_1.png',
            caption=figure_details['fig1']['caption'], 
            label=figure_details['fig1']['label']
        )
        
        # FIGURE 2:
        # Create the figure using matplotlib and seaborn
        fig2, ax2 = plt.subplots()
        sns.scatterplot(data=df, x='variable_y', y='variable_z', ax=ax2)
        # Save the figure with caption and label
        to_latex_figure_with_caption(
            fig2, 'figure_2.png',
            caption=figure_details['fig2']['caption'], 
            label=figure_details['fig2']['label']
        )
        
        # FIGURE ?:
        # <etc, all figures required>
        Avoid the following:
        
        Do not provide a sketch or pseudocode; write complete runnable code including all '# HEADERS' sections.
        Do not create any tables or other output; only create figures.
        Do not send any presumed output examples.
        ''')

    code_review_prompts: Collection[CodeReviewPrompt] = ()
