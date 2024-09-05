from dataclasses import dataclass, field
import numbers
import re
from typing import Dict, Union, Optional, List, Any, Tuple, Type, ClassVar, Callable

import numpy as np
import pandas as pd

from data_to_paper.env import PRINT_DEBUG_COMMENTS
from data_to_paper.llm_coding_utils.df_to_figure import ALLOWED_PLOT_KINDS
from data_to_paper.llm_coding_utils.df_to_latex import df_to_latex
from data_to_paper.run_gpt_code.base_run_contexts import RegisteredRunContext
from data_to_paper.run_gpt_code.overrides.dataframes.df_with_attrs import ListInfoDataFrame
from data_to_paper.run_gpt_code.run_contexts import ProvideData

from data_to_paper.utils import dedent_triple_quote_str
from data_to_paper.utils.dataframe import extract_df_row_labels, extract_df_column_labels, extract_df_axes_labels
from data_to_paper.utils.numerics import is_lower_eq

from data_to_paper.research_types.hypothesis_testing.env import get_max_rows_and_columns, MAX_BARS
from data_to_paper.run_gpt_code.overrides.dataframes.utils import df_to_llm_readable_csv
from data_to_paper.run_gpt_code.overrides.pvalue import is_p_value, PValue, is_containing_p_value, is_only_p_values, \
    OnStrPValue, OnStr
from data_to_paper.run_gpt_code.run_issues import CodeProblem, RunIssue, RunIssues
from data_to_paper.utils.types import ListBasedSet
from .abbreviations import is_unknown_abbreviation
from .utils import is_non_integer_numeric, _find_longest_labels_in_index, \
    _find_longest_labels_in_columns_relative_to_content


@dataclass
class BaseChecker:

    issues: RunIssues = field(default_factory=RunIssues)
    intermediate_results: Dict[str, Any] = field(default_factory=dict)
    stop_after_first_issue: bool = False

    def _append_issue(self, category: str = None, item: str = None, issue: str = '', instructions: str = '',
                      code_problem: CodeProblem = None, forgive_after: Optional[int] = None):
        self.issues.append(RunIssue(
            category=category,
            item=item,
            issue=issue,
            instructions=instructions,
            code_problem=code_problem,
            forgive_after=forgive_after,
        ))

    def _automatically_get_all_check_methods(self):
        return [getattr(type(self), method_name) for method_name in dir(self) if method_name.startswith('check')]

    def _assert_if_provided_choice_of_checks_include_all_check_methods(self):
        if self.CHOICE_OF_CHECKS is not None:
            for check_method in self._automatically_get_all_check_methods():
                assert check_method in self.CHOICE_OF_CHECKS, f'Missing check method: {check_method.__name__}'

    def _get_checks_to_run(self):
        if self.CHOICE_OF_CHECKS is None:
            return self._automatically_get_all_check_methods()
        return [check for check, should_check in self.CHOICE_OF_CHECKS.items() if should_check]

    def _run_checks(self):
        self._assert_if_provided_choice_of_checks_include_all_check_methods()
        for check in self._get_checks_to_run():
            num_issues_before = len(self.issues)
            should_stop = check(self)
            num_created_issues = len(self.issues) - num_issues_before
            if should_stop and not num_created_issues:
                assert False, f'Check {check.__name__} returned True, but no issues were created.'
            if PRINT_DEBUG_COMMENTS:
                print(f'Check "{check.__name__}" created {num_created_issues} issues.')
            if self.issues and (self.stop_after_first_issue or should_stop):
                break

    def run_checks(self) -> Tuple[RunIssues, Dict[str, Any]]:
        self._run_checks()
        return self.issues, self.intermediate_results

    CHOICE_OF_CHECKS: ClassVar[Optional[Dict[Callable, bool]]] = None


@dataclass
class ChainChecker(BaseChecker):
    checkers: List[BaseChecker] = None
    stop_after_first_issue: bool = True

    def _run_checks(self):
        for checker in self.checkers:
            checker.intermediate_results.update(self.intermediate_results)
            issues, intermediate_results = checker.run_checks()
            self.issues.extend(issues)
            self.intermediate_results.update(intermediate_results)
            if issues and self.stop_after_first_issue:
                break


def create_and_run_chain_checker(checkers: List[Type[BaseChecker]], stop_after_first_issue: bool = True, **kwargs
                                 ) -> Tuple[RunIssues, Dict[str, Any]]:
    chain_checker = ChainChecker(checkers=[checker(**kwargs) for checker in checkers],  # type: ignore
                                 stop_after_first_issue=stop_after_first_issue)
    return chain_checker.run_checks()


@dataclass
class BaseDfChecker(BaseChecker):
    func_name: str = 'df_to_figure/df_to_latex'
    df: pd.DataFrame = None
    filename: str = None
    kwargs: dict = field(default_factory=dict)

    DEFAULT_CATEGORY: ClassVar[str] = None
    DEFAULT_CODE_PROBLEM: ClassVar[CodeProblem] = None

    def _append_issue(self, category: str = None, item: str = None, issue: str = '', instructions: str = '',
                      code_problem: CodeProblem = None, forgive_after: Optional[int] = None):
        category = self.DEFAULT_CATEGORY if category is None else category
        code_problem = self.DEFAULT_CODE_PROBLEM if code_problem is None else code_problem
        item = self.filename if item is None else item
        super()._append_issue(category=category, item=item, issue=issue, instructions=instructions,
                              code_problem=code_problem, forgive_after=forgive_after)

    @property
    def is_figure(self):
        return self.func_name == 'df_to_figure'

    @property
    def table_or_figure(self):
        return 'figure' if self.is_figure else 'table'

    @property
    def index(self) -> bool:
        if self.is_figure:
            return self.kwargs.get('use_index', True) and self.x is None
        else:
            return self.kwargs.get('index', True)

    @property
    def note(self) -> Optional[str]:
        return self.kwargs.get('note', None)

    @property
    def glossary(self) -> Optional[Dict[str, str]]:
        return self.kwargs.get('glossary', None)

    @property
    def caption(self) -> Optional[str]:
        return self.kwargs.get('caption', None)

    @property
    def kind(self) -> Optional[str]:
        return self.kwargs.get('kind', None)

    @property
    def x(self) -> Optional[str]:
        return self.kwargs.get('x', None)

    @property
    def y(self) -> Optional[Union[str, List[str]]]:
        return self.kwargs.get('y', None)

    @property
    def yerr(self) -> Optional[Union[str, List[str]]]:
        return self.kwargs.get('yerr', None)

    @property
    def xerr(self) -> Optional[str]:
        return self.kwargs.get('yerr', None)

    @property
    def y_ci(self) -> Optional[Union[str, List[str]]]:
        return self.kwargs.get('y_ci', None)

    @property
    def x_ci(self) -> Optional[str]:
        return self.kwargs.get('x_ci', None)

    @property
    def y_p_value(self) -> Optional[Union[str, List[str]]]:
        return self.kwargs.get('y_p_value', None)

    @property
    def x_p_value(self) -> Optional[str]:
        return self.kwargs.get('x_p_value', None)

    def get_xy_err_ci_p_value(self, x_or_y: str, as_list=False):
        xy = getattr(self, x_or_y)
        err = getattr(self, f'{x_or_y}err')
        ci = getattr(self, f'{x_or_y}_ci')
        p_value = getattr(self, f'{x_or_y}_p_value')
        if as_list:
            xy = [xy] if isinstance(xy, str) else xy
            err = [err] if isinstance(err, str) else err
            ci = [ci] if isinstance(ci, str) else ci
            p_value = [p_value] if isinstance(p_value, str) else p_value
        return xy, err, ci, p_value

    CHOICE_OF_CHECKS = {}


""" SYNTAX """


@dataclass
class SyntaxDfChecker(BaseDfChecker):
    """
    Checks that do not depend on the content of df.
    """
    DEFAULT_CATEGORY = 'Checking df_to_figure/df_to_latex for call syntax'
    DEFAULT_CODE_PROBLEM = CodeProblem.OutputFileCallingSyntax

    def check_filename(self):
        """
        Check if the filename of in the format `df_<alphanumeric>`.
        """
        if not re.match(pattern=r'^df_\w+$', string=self.filename):
            self._append_issue(
                issue=f'The filename of the {self.table_or_figure} should be in the format `df_<alphanumeric>`, '
                      f'but got "{self.filename}".',
            )

    def check_no_label(self):
        if self.kwargs.get('label', None):
            self._append_issue(
                issue=f'The `label` argument should not be used in `df_to_figure` or `df_to_latex`; '
                      f'It is automatically generated from the filename.',
                instructions='Please remove the `label` argument.',
            )
    CHOICE_OF_CHECKS = BaseDfChecker.CHOICE_OF_CHECKS | {
        check_filename: True,
        check_no_label: True,
    }


@dataclass
class TableSyntaxDfChecker(SyntaxDfChecker):
    func_name: str = 'df_to_latex'

    def check_that_index_is_true(self):
        if not self.index:
            self._append_issue(
                issue='Do not call `df_to_latex` with `index=False`.',
                instructions=dedent_triple_quote_str("""
                    Please revise the code making sure all tables are created with `index=True`, \t
                    and that the index is meaningful.
                    """)
            )

    def check_column_arg_is_not_used(self):
        if 'columns' in self.kwargs:
            self._append_issue(
                issue='Do not use the `columns` argument in `df_to_latex`.',
                instructions='If you want to drop columns, do it before calling `df_to_latex`.',
            )

    CHOICE_OF_CHECKS = SyntaxDfChecker.CHOICE_OF_CHECKS | {
        check_that_index_is_true: True,
        check_column_arg_is_not_used: True,
    }


@dataclass
class FigureSyntaxDfChecker(SyntaxDfChecker):
    func_name: str = 'df_to_figure'

    def check_kind_arg(self):
        """
        Check if the plot kind is one of the allowed plot kinds.
        """
        if self.kind is None:
            self._append_issue(
                issue=f'Plot `kind` is not specified.',
                instructions=f'Please explicitly specify the `kind` argument. available options are:\n'
                             f'{ALLOWED_PLOT_KINDS}.',
            )
        elif self.kind not in ALLOWED_PLOT_KINDS:
            self._append_issue(
                issue=f'Plot kind "{self.kind}" is not supported.',
                instructions=f'Only use these kinds: {ALLOWED_PLOT_KINDS}.',
            )

    def check_y_arg(self):
        if self.y is None:
            self._append_issue(
                issue=f'No y values are specified.',
                instructions='Please use the `y` argument to specify the columns to be plotted.',

            )

    def check_yerr_arg(self):
        if self.yerr is not None:
            self._append_issue(
                issue=f'Do not use the `yerr` argument in `df_to_figure`.',
                instructions='Instead, directly indicate the confidence intervals using the `y_ci` argument.',
            )

    def check_that_specified_columns_exist(self):
        """
        Check if the columns specified in the `y` and `yerr` arguments exist in the df.
        """
        base_arg_names = ['', 'err', '_ci', '_p_value']
        for xy in ['x', 'y']:
            args = self.get_xy_err_ci_p_value(xy, as_list=True)
            arg_names = [xy + arg_name for arg_name in base_arg_names]
            for arg, arg_name in zip(args, arg_names):
                if arg is None:
                    continue
                un_specified_columns = [col for col in arg if col not in self.df.columns]
                if un_specified_columns:
                    self._append_issue(
                        issue=f'The columns {un_specified_columns} specified in the `{arg_name}` argument do not exist '
                              f'in the df.',
                        instructions=f'Available columns are: {self.df.columns}.',
                    )

    CHOICE_OF_CHECKS = SyntaxDfChecker.CHOICE_OF_CHECKS | {
        check_kind_arg: True,
        check_y_arg: True,
        check_yerr_arg: True,
        check_that_specified_columns_exist: True,
    }


""" CONTENT FOR ANALYSIS STEP """


@dataclass
class BaseContentDfChecker(BaseDfChecker):
    stop_after_first_issue: bool = True

    prior_dfs: Dict[str, pd.DataFrame] = field(default_factory=dict)

    ALLOWED_VALUE_TYPES = (numbers.Number, str, bool, tuple, PValue)
    ALLOWED_COLUMN_AND_INDEX_TYPES = {'columns': (int, str, bool), 'index': (int, str, bool)}
    ALLOW_MULTI_INDEX_FOR_COLUMN_AND_INDEX = {'columns': True, 'index': True}

    DEFAULT_CATEGORY = 'Checking content of created dfs'
    DEFAULT_CODE_PROBLEM = CodeProblem.OutputFileContentA

    def _get_x_values(self):
        if self.is_figure:
            x = self.x
            if x is None:
                return self.df.index
            return self.df[x]
        else:
            if self.index:
                return self.df.index
            # if the index is not used, it is the first column that behaves as the index:
            return self.df.iloc[:, 0]

    def _get_max_rows_and_columns(self):
        return get_max_rows_and_columns(self.is_figure, kind=self.kind, to_show=False)


@dataclass
class DfContentChecker(BaseContentDfChecker):
    VALUES_CATEGORY = 'Problem with df values'
    INDEX_COLUMN_CATEGORY = 'Problem with df index/columns'
    SIZE_CATEGORY = 'Too large df'

    def _check_if_df_within_df(self) -> bool:
        for value in self.df.values.flatten():
            if isinstance(value, (pd.Series, pd.DataFrame)):
                self._append_issue(
                    category=self.VALUES_CATEGORY,
                    issue=f"Something wierd in your dataframe. Iterating over df.values.flatten() "
                          f"returned a `{type(value).__name__}` object.",
                )
                return True
        return False

    def check_df_value_types(self):
        """
        Check if the dataframe has only allowed value types.
        """
        if self._check_if_df_within_df():
            return
        un_allowed_type_names = {f'{type(value).__name__}' for value in self.df.values.flatten()
                                 if not isinstance(value, self.ALLOWED_VALUE_TYPES)}
        if un_allowed_type_names:
            self._append_issue(
                category=self.VALUES_CATEGORY,
                issue=f"Your dataframe contains values of types {sorted(un_allowed_type_names)} which are not allowed.",
                instructions=f"Please make sure the saved dataframes have only numeric, str, bool, or tuple values.",
            )

    def check_df_for_nan_values(self):
        """
        Check if the df has NaN values or PValue with value of nan
        """
        df_with_raw_pvalues = self.df.applymap(lambda v: v.value if is_p_value(v) else v)
        isnull = pd.isnull(df_with_raw_pvalues)
        num_nulls = isnull.sum().sum()
        if num_nulls > 0:
            issue_text = f'Note that the df has {num_nulls} NaN value(s).'
            if len(isnull) < 20:
                issue_text += f'\nHere is the `isnull` of the df:'
            else:
                # show only the first 10 rows with NaN values:
                isnull = self.df[isnull.any(axis=1)].head(10)
                issue_text += f'\nHere are some example lines with NaN values:'
            issue_text += f'\n```\n{df_to_llm_readable_csv(isnull)}\n```\n'
            instructions = \
                f"Please revise the code to avoid NaN values in the created {self.table_or_figure}."
            if not self.is_figure:
                instructions += \
                    "\nIf the NaNs are legit and stand for missing values: replace them with the string '-'.\n" \
                    "Otherwise, if they are computational errors, please revise the code to fix it."
            self._append_issue(
                category=self.VALUES_CATEGORY,
                issue=issue_text,
                instructions=instructions
            )

    @staticmethod
    def _get_unsupported_df_header_types(headers: Union[pd.MultiIndex, pd.Index], allowed_types: Tuple[Type]
                                         ) -> ListBasedSet[Any]:
        """
        Find any headers of the dataframe are int, str, or bool.
        """
        if isinstance(headers, pd.MultiIndex):
            headers = [label for level in range(headers.nlevels) for label in headers.get_level_values(level)]

        return ListBasedSet(type(header) for header in headers if not isinstance(header, allowed_types))

    def check_df_headers_type(self):
        for column_or_index in ['columns', 'index']:
            headers = getattr(self.df, column_or_index)

            # Check if the headers are a multi-index and if it is allowed:
            if not self.ALLOW_MULTI_INDEX_FOR_COLUMN_AND_INDEX[column_or_index] and isinstance(headers, pd.MultiIndex):
                self._append_issue(
                    category=self.INDEX_COLUMN_CATEGORY,
                    issue=f"Your dataframe has a multi-index for the {column_or_index}.",
                    instructions=f"Please make sure the df has a single-level {column_or_index}.",
                )
                continue

            # Check if the headers are of the allowed types:
            allowed_types = self.ALLOWED_COLUMN_AND_INDEX_TYPES[column_or_index]
            unsupported_header_types = self._get_unsupported_df_header_types(headers, allowed_types)
            if unsupported_header_types:
                self._append_issue(
                    category=self.INDEX_COLUMN_CATEGORY,
                    issue=f"Your df has {column_or_index} headers of unsupported types: {unsupported_header_types}.",
                    instructions=f"The df {column_or_index} headers should be {allowed_types}.",
                )

    def check_df_index_is_a_range(self):
        """
        Check if the index of the dataframe is just a numeric range.
        """
        if not self.index:
            return
        num_rows = self.df.shape[0]
        index_is_range = not isinstance(self.df.index, pd.MultiIndex) \
            and [ind for ind in self.df.index] == list(range(num_rows)) and self.df.index.dtype == int
        if index_is_range:
            if self.is_figure:
                issue = dedent_triple_quote_str(f"""
                    We are using the index of the df as the x-values of the plot.
                    But, the index of df "{self.filename}" is just a range from 0 to {num_rows - 1}.
                    """)
                instructions = dedent_triple_quote_str(f"""
                    Please revise the code making sure the figure is built with an index that represents meaningful \t
                    numeric data. Or, for categorical data, the index should be a list of strings.
                    """)
            else:
                issue = dedent_triple_quote_str(f"""
                    The index of the df is used by `df_to_latex` as the row labels.
                    But, the index of df "{self.filename}" is just a range from 0 to {num_rows - 1}.
                    """)
                instructions = dedent_triple_quote_str(f"""
                    Please revise the code making sure the df is built with an index that has \t
                    meaningful row labels.
                    Labeling row with sequential numbers is not common in scientific tables. 
                    Though, if you are sure that starting each row with a sequential number is really what you want, \t
                    then convert it from int to strings, so that it is clear that it is not a mistake.
                    """)
            self._append_issue(
                category=self.INDEX_COLUMN_CATEGORY,
                issue=issue,
                instructions=instructions,
            )

    def check_df_size(self):
        """
        Check if the df has too many columns or rows
        """
        shape = self.df.shape
        max_rows_and_columns = self._get_max_rows_and_columns()
        if is_lower_eq(shape[0], max_rows_and_columns[0]) and is_lower_eq(shape[1], max_rows_and_columns[1]):
            return
        if is_lower_eq(shape[0], max_rows_and_columns[1]) and is_lower_eq(shape[1], max_rows_and_columns[0]):
            transpose_note = "You might also consider transposing the df.\n"
        else:
            transpose_note = ""
        max_rows, max_columns = max_rows_and_columns
        trimming_note = f"Note that simply trimming the data is not always a good solution. " \
                        f"You might instead consider a different representation/organization " \
                        f"of the presented data.\n"
        if not self.is_figure:
            trimming_note += "Or, consider representing the data as a figure.\n"
        for ax, rows_or_columns in enumerate(('rows', 'columns')):
            if not is_lower_eq(shape[ax], max_rows_and_columns[ax]):
                self._append_issue(
                    category=self.SIZE_CATEGORY,
                    issue=f'The {self.table_or_figure} df has {shape[ax]} {rows_or_columns}, which is too many for '
                          f'our {self.table_or_figure} (max allowed: {max_rows_and_columns[ax]}).',
                    instructions=f"Please revise the code so that df of created {self.table_or_figure} "
                                 f"have a maximum of {max_rows} rows and {max_columns} columns.\n"
                                 + trimming_note + transpose_note,
                )

    CHOICE_OF_CHECKS = BaseDfChecker.CHOICE_OF_CHECKS | {
        check_df_for_nan_values: True,
        check_df_value_types: True,
        check_df_headers_type: True,
        check_df_index_is_a_range: True,
        check_df_size: True,
    }


@dataclass
class TableDfContentChecker(DfContentChecker):
    func_name: str = 'df_to_latex'

    OVERLAYING_VALUES_CATEGORY = 'Overlapping values'
    DF_DISPLAY_CATEGORY = 'The df looks like a df.describe() table, not a scientific table'

    def check_df_is_a_result_of_describe(self):
        """
        Check if the table is a df.describe() table
        """
        description_labels = ('mean', 'std', 'min', '25%', '50%', '75%', 'max')
        if set(description_labels).issubset(self.df.columns) or set(description_labels).issubset(self.df.index):
            self._append_issue(
                category=self.DF_DISPLAY_CATEGORY,
                issue=f'The df includes mean, std, as well as quantiles and min/max values.',
                instructions=dedent_triple_quote_str("""
                    Note that in scientific tables, it is not customary to include quantiles, or min/max values, \t
                    especially if the mean and std are also included.
                    Please revise the code so that the tables only include scientifically relevant statistics.
                    """),
                forgive_after=3,
            )

    def check_df_for_repeated_values(self):
        """
        # Check if the table contains the same values in multiple cells
        """
        df_values = [v for v in self.df.values.flatten() if is_non_integer_numeric(v)]
        if len(df_values) != len(set(df_values)):
            # Find the positions of the duplicated values:
            duplicated_values = [v for v in df_values if df_values.count(v) > 1]
            example_value = duplicated_values[0]
            duplicated_value_positions = np.where(self.df.values == example_value)
            duplicated_value_positions = list(zip(*duplicated_value_positions))
            duplicated_value_positions = [f'({row}, {col})' for row, col in duplicated_value_positions]
            duplicated_value_positions = ', '.join(duplicated_value_positions)

            self._append_issue(
                category=self.OVERLAYING_VALUES_CATEGORY,
                issue=f'Note that the df "{self.filename}" includes the same values in multiple cells.\n'
                      f'For example, the value {example_value} appears in the following cells:\n'
                      f'{duplicated_value_positions}.',
                instructions=dedent_triple_quote_str("""
                    This is likely a mistake and is surely confusing to the reader.
                    Please revise the code so that the df does not repeat the same values in multiple cells.
                    """),
                forgive_after=1,
            )

    def check_df_for_repeated_values_in_prior_dfs(self):
        """
        Check if the df numeric values overlap with values in prior dfs
        """
        if not self.prior_dfs:
            return
        df_values = [v for v in self.df.values.flatten() if is_non_integer_numeric(v)]
        for prior_name, prior_table in self.prior_dfs.items():
            if prior_table is self.df:
                continue
            prior_table_values = [v for v in prior_table.values.flatten() if is_non_integer_numeric(v)]
            if any(value in prior_table_values for value in df_values):
                self._append_issue(
                    category=self.OVERLAYING_VALUES_CATEGORY,
                    issue=f'Table "{self.filename}" includes values that overlap with values in table "{prior_name}".',
                    instructions=dedent_triple_quote_str("""
                        In scientific tables, it is not customary to include the same values in multiple tables.
                        Please revise the code so that each table include its own unique data.
                        """),
                    forgive_after=1,
                )

    CHOICE_OF_CHECKS = {
        check_df_is_a_result_of_describe: True,  # We want to start with detecting describe tables.
        check_df_for_repeated_values: True,
        check_df_for_repeated_values_in_prior_dfs: True,
    } | DfContentChecker.CHOICE_OF_CHECKS


@dataclass
class FigureDfContentChecker(DfContentChecker):
    func_name: str = 'df_to_figure'
    ALLOWED_COLUMN_AND_INDEX_TYPES = {'columns': (str,), 'index': (int, str, bool, float)}
    ALLOW_MULTI_INDEX_FOR_COLUMN_AND_INDEX = {'columns': False, 'index': False}

    DEFAULT_CATEGORY = 'Checking figure'
    P_VALUE_CATEGORY = 'Plotting P-values'

    def check_that_y_values_are_numeric(self):
        y, yerr, y_ci, y_p_value = self.get_xy_err_ci_p_value('y', as_list=True)
        for column in y:
            if not pd.api.types.is_numeric_dtype(self.df[column]):
                self._append_issue(
                    issue=f'Column `{column}` is not numeric, so it is not suitable for a plot.',
                    instructions='All columns specified by the `y` argument must have numeric values.',
                )

    def check_for_p_values_in_figure(self):
        """
        If the df has p-values, they must be plotted using the argument `x_p_value` or `y_p_value`.
        """
        if self.x_p_value:
            self._append_issue(
                category=self.P_VALUE_CATEGORY,
                issue='The `x_p_value` argument is not supported.',
                instructions='Please use the `y_p_value` argument instead.',
            )
            return
        if self.y_p_value is None:
            return

        p_value_columns = [col for col in self.df.columns if is_containing_p_value(self.df[col])]

        # check that the columns with p-values only contain p-values:
        not_pure_p_values = [col for col in p_value_columns if not is_only_p_values(self.df[col])]
        if not_pure_p_values:
            self._append_issue(
                category=self.P_VALUE_CATEGORY,
                issue=f'The df has columns {not_pure_p_values}, which contain p-values and non-p-values.',
                instructions='Please make sure that the columns with p-values only contain p-values.',
            )
            return

        if self.x_p_value is not None and self.y_p_value is not None:
            self._append_issue(
                category=self.P_VALUE_CATEGORY,
                issue='Both `x_p_value` and `y_p_value` are set.',
                instructions='Please use only one of them.',
            )
            return

        y, yerr, y_ci, y_p_value = self.get_xy_err_ci_p_value('y', as_list=True)

        chosen_columns_are_not_p_values = [col for col in y_p_value if col not in p_value_columns]
        if chosen_columns_are_not_p_values:
            self._append_issue(
                category=self.P_VALUE_CATEGORY,
                issue=f'The columns y_p_value={chosen_columns_are_not_p_values} are not p-values.',
                instructions='Please make sure that the columns with p-values only contain p-values.',
            )

        p_value_columns_not_in_y_p_value = [col for col in p_value_columns if col not in y_p_value]
        if p_value_columns_not_in_y_p_value:
            self._append_issue(
                category=self.P_VALUE_CATEGORY,
                issue=f'The columns {p_value_columns_not_in_y_p_value} contain p-values but are not in y_p_value.',
                instructions='Please include all the columns with p-values in y_p_value argument, or remove them '
                             'from the df.',
                forgive_after=1,
            )

    def check_for_max_number_of_bars(self):
        if self.kind not in ['bar', 'barh']:
            return
        y, yerr, y_ci, y_p_value = self.get_xy_err_ci_p_value('y', as_list=True)
        n_bars = len(self.df) * len(y)
        if not is_lower_eq(n_bars, MAX_BARS):
            self._append_issue(
                issue=f'The plot has {n_bars} bars, which is a large number.',
                instructions='Consider reducing the number of bars to make the plot more readable.',
                forgive_after=2,
            )

    def check_that_y_values_are_diverse(self):
        # There is no point in plotting a box, violin, hist if the y values are not diverse
        if self.kind not in ['box', 'violin', 'hist']:
            return
        y, yerr, y_ci, y_p_value = self.get_xy_err_ci_p_value('y', as_list=True)
        for column in y:
            n_unique = self.df[column].nunique()
            if n_unique <= 2:
                self._append_issue(
                    issue=f'Column `{column}` has only {n_unique} unique values, so it is not suitable for '
                          f'a "{self.kind}" plot.',
                    instructions='Choose another kind of plot, like calculating the mean and plotting a bar plot.',
                )

    def check_for_numeric_x_for_line_and_scatter(self):
        """check that we do not have non-numeric x:"""
        if self.kind not in ['line', 'scatter']:
            return
        if not pd.api.types.is_numeric_dtype(self._get_x_values()):
            self._append_issue(
                issue=f'The x values are not numeric, so they are not suitable for a "{self.kind}" plot.',
                instructions='Consider another kind of plot, like a bar plot (kind="bar").',
            )

    CHOICE_OF_CHECKS = DfContentChecker.CHOICE_OF_CHECKS | {
        check_that_y_values_are_numeric: True,
        check_for_p_values_in_figure: True,
        check_for_max_number_of_bars: True,
        check_that_y_values_are_diverse: True,
        check_for_numeric_x_for_line_and_scatter: True,
    }


""" COMPILATION """


@dataclass
class CompilationDfContentChecker(BaseContentDfChecker):
    intermediate_results: Dict[str, Any] = field(default_factory=lambda: {'width': None})


@dataclass
class FigureCompilationDfContentChecker(CompilationDfContentChecker):
    func_name: str = 'df_to_figure'


@dataclass
class TableCompilationDfContentChecker(CompilationDfContentChecker):
    func_name: str = 'df_to_latex'

    def _df_to_latex_transpose(self):
        assert 'columns' not in self.kwargs, "assumes columns is None"
        kwargs = self.kwargs.copy()
        index = kwargs.pop('index', True)
        header = kwargs.pop('header', True)
        header, index = index, header
        return df_to_latex(self.df.T, self.filename, index=index, header=header, **kwargs)

    def check_compilation_and_get_width(self):
        try:
            compilation_func = ProvideData.get_item('compile_to_pdf_func')
        except RuntimeError:
            compilation_func = None

        with RegisteredRunContext.temporarily_disable_all():
            with OnStrPValue(OnStr.SMALLER_THAN):
                latex = df_to_latex(self.df, self.filename, **self.kwargs)
            if compilation_func is None:
                e = 0.
            else:
                e = compilation_func(latex, self.filename)

        # save the width of the table:
        self.intermediate_results['width'] = e

        if not isinstance(e, float):
            self._append_issue(
                category='Table pdflatex compilation failure',
                issue=dedent_triple_quote_str("""
                    Here is the created table:

                    ```latex
                    {table}
                    ```

                    When trying to compile it using pdflatex, I got the following error:

                    {error}

                    """).format(filename=self.filename, table=latex, error=e),
            )
        elif e > 1.3:
            # table is too wide
            # Try to compile the transposed table:
            with OnStrPValue(OnStr.SMALLER_THAN):
                latex_transpose = self._df_to_latex_transpose()
            with RegisteredRunContext.temporarily_disable_all():
                e_transpose = compilation_func(latex_transpose, self.filename + '_transpose')
            if isinstance(e_transpose, float) and e_transpose < 1.1:
                transpose_message = '- Alternatively, consider completely transposing the table. Use `df = df.T`.'
            else:
                transpose_message = ''
            index_note = ''
            column_note = ''
            if self.index:
                longest_index_labels = _find_longest_labels_in_index(self.df.index)
                longest_index_labels = [label for label in longest_index_labels if label is not None and len(label) > 6]
                with OnStrPValue(OnStr.SMALLER_THAN):
                    longest_column_labels = _find_longest_labels_in_columns_relative_to_content(self.df)
                longest_column_labels = [label for label in longest_column_labels if len(label) > 6]
                if longest_index_labels:
                    index_note = dedent_triple_quote_str(f"""\n
                        - Rename any long index labels to shorter names \t
                        (for instance, some long label(s) in the index are: {longest_index_labels}). \t
                        Use `df.rename(index=...)`
                        """)

                if longest_column_labels:
                    column_note = dedent_triple_quote_str(f"""\n
                        - Rename any long column labels to shorter names \t
                        (for instance, some long label(s) in the columns are: {longest_column_labels}). \t
                        Use `df.rename(columns=...)`
                        """)

            if not index_note and not column_note and not transpose_message:
                drop_column_message = dedent_triple_quote_str("""\n
                    - Drop unnecessary columns. \t
                    If the labels cannot be shortened much, consider whether there might be any \t
                    unnecessary columns that we can drop. \t
                    Use `df_to_latex(df, filename, columns=...)`.
                    """)
            else:
                drop_column_message = ''

            self._append_issue(
                category='Table too wide',
                issue=dedent_triple_quote_str("""
                    Here is the created table:

                    ```latex
                    {table}
                    ```
                    I tried to compile it, but the table is too wide. 
                    """).format(filename=self.filename, table=latex),
                instructions="Please change the code to make the table narrower. "
                             "Consider any of the following options:\n"
                             + index_note + column_note + drop_column_message + transpose_message,
            )
        else:
            # table is fine
            pass

    CHOICE_OF_CHECKS = BaseDfChecker.CHOICE_OF_CHECKS | {
        check_compilation_and_get_width: True,
    }


""" CONTENT FOR DISPLAY-ITEM STEP """


@dataclass
class SecondTableContentChecker(BaseContentDfChecker):
    func_name: str = 'df_to_latex'

    def check_for_repetitive_value_in_column(self):
        for icol in range(self.df.shape[1]):
            column_label = self.df.columns[icol]
            data = self.df.iloc[:, icol]
            if is_containing_p_value(data):
                continue
            try:
                data_unique = data.unique()
            except Exception:  # noqa
                data_unique = None
            if data_unique is not None and len(data_unique) == 1 and len(data) > 5:
                data0 = data.iloc[0]
                # check if the value is a number
                if not isinstance(data0, (int, float)):
                    pass
                elif round(data0) == data0 and data0 < 10:
                    pass
                else:
                    self._append_issue(
                        category='Same value throughout a column',
                        issue=f'The column "{column_label}" has the same unique value for all rows.',
                        instructions=dedent_triple_quote_str(f"""
                            Please revise the code so that it:
                            * Finds the unique values (use `{column_label}_unique = df["{column_label}"].unique()`)
                            * Asserts that there is only one value. (use `assert len({column_label}_unique) == 1`)
                            * Drops the column from the df (use `df.drop(columns=["{column_label}"])`)
                            * Adds the unique value, {column_label}_unique[0], \t
                            in the {self.table_or_figure} note \t
                            (e.g., `{self.func_name}(..., note=f'For all rows, \t
                            the {column_label} is {{{column_label}_unique[0]}}')`)

                            There is no need to add corresponding comments to the code. 
                            """),
                    )

    CHOICE_OF_CHECKS = BaseDfChecker.CHOICE_OF_CHECKS | {
        check_for_repetitive_value_in_column: True,
    }


@dataclass
class SecondFigureContentChecker(BaseContentDfChecker):
    func_name: str = 'df_to_figure'

    ODDS_RATIO_TERMS_CAPS = [('odds ratio', False), ('OR', True)]

    def check_log_scale_for_odds_ratios(self):
        """
        Odds ratios should typically be plotted on a log scale.
        Check if the x or y label contains the term "odds ratio".
        """
        for axis in ['x', 'y']:
            label = self.kwargs.get(axis + 'label')
            is_log = self.kwargs.get('log' + axis)
            if label is not None and is_log is not True:
                for term, is_caps in self.ODDS_RATIO_TERMS_CAPS:
                    modified_label = label.lower() if not is_caps else label
                    if term in modified_label:
                        self._append_issue(
                            category='Plotting odds ratios',
                            issue=f'The {axis}-axis label contains the term "{term}". Are you plotting odds ratios?\n'
                                  f'If so, odds ratios are typically shown on a log scale; '
                                  f'consider using a log scale for the {axis}-axis.',
                            instructions=f'Consider using a log scale for the {axis}-axis (setting `log{axis}=True`).',
                            forgive_after=1,
                        )
                        break

    CHOICE_OF_CHECKS = BaseDfChecker.CHOICE_OF_CHECKS | {
        check_log_scale_for_odds_ratios: True,
    }


""" ANNOTATION """


@dataclass
class AnnotationDfChecker(BaseContentDfChecker):
    stop_after_first_issue: bool = False

    UN_ALLOWED_CHARS = [
        ('_', 'underscore'),
        ('^', 'caret'),
        ('{', 'curly brace'),
        ('}', 'curly brace')
    ]

    @property
    def width(self):
        return self.intermediate_results.get('width')

    @property
    def is_narrow(self):
        return isinstance(self.width, float) and self.width < 0.8

    def check_for_unallowed_characters_in_labels(self):
        for char, char_name in self.UN_ALLOWED_CHARS:
            for is_row in [True, False]:
                if is_row:
                    labels = extract_df_row_labels(self.df, with_title=True, string_only=True)
                    index_or_columns = 'index'
                else:
                    labels = extract_df_column_labels(self.df, with_title=True, string_only=True)
                    index_or_columns = 'columns'
                unallowed_labels = sorted([label for label in labels if char in label])
                if unallowed_labels:
                    self._append_issue(
                        category=f'The df row/column labels contain un-allowed characters',
                        issue=dedent_triple_quote_str(f"""
                            The "{self.filename}" has {index_or_columns} labels containing \t
                            the character "{char}" ({char_name}), which is not allowed.
                            Here are the problematic {index_or_columns} labels:
                            {unallowed_labels}
                            """),
                        instructions=dedent_triple_quote_str(f"""
                            Please revise the code to map these {index_or_columns} labels to new names \t
                            that do not contain the "{char}" characters. Spaces are allowed.

                            Doublecheck to make sure your code uses `df.rename({index_or_columns}=...)` \t
                            with the `{index_or_columns}` argument set to a dictionary mapping the old \t
                            {index_or_columns} names to the new ones.
                            """)
                    )

    def check_for_abbreviations_not_in_glossary(self):
        axes_labels = extract_df_axes_labels(self.df, with_title=False, string_only=True)
        abbr_labels = [label for label in axes_labels if is_unknown_abbreviation(label)]
        glossary = self.glossary or {}
        un_mentioned_abbr_labels = sorted([label for label in abbr_labels if label not in glossary])
        if un_mentioned_abbr_labels:
            instructions = dedent_triple_quote_str(f"""
                Please revise the code making sure all abbreviated labels (of both column and rows!) are explained \t
                in the glossary.
                Add the missing abbreviations and their explanations as keys and values in the `glossary` \t
                argument of `df_to_latex` or `df_to_figure`.
                """)
            if self.is_narrow:
                instructions += dedent_triple_quote_str(f"""
                    Alternatively, since the {self.table_or_figure} is not too wide, you can also replace the \t
                    abbreviated labels with their full names in the dataframe itself.
                    """)
            if self.glossary:
                issue = dedent_triple_quote_str(f"""
                    The `glossary` argument of `{self.func_name}` includes only the following keys:
                    {list(self.glossary.keys())}
                    We need to add also the following abbreviated row/column labels:
                    {un_mentioned_abbr_labels}
                    """)
            else:
                issue = dedent_triple_quote_str(f"""
                    The {self.table_or_figure} needs a glossary explaining the following abbreviated labels:
                    {un_mentioned_abbr_labels}
                    """)
            self._append_issue(
                category='Displayitem glossary',
                issue=issue,
                instructions=instructions,
            )

    def check_for_glossary_labels_not_in_df(self):
        if not self.glossary:
            return
        all_labels = extract_df_axes_labels(self.df, with_title=True, string_only=True)
        un_mentioned_labels = [label for label in self.glossary if label not in all_labels and label != 'Significance']
        if un_mentioned_labels:
            self._append_issue(
                category='Displayitem glossary',
                issue=f'The glossary of the {self.func_name} includes the following labels that are not in the df:\n'
                      f'{un_mentioned_labels}\n'
                      f'Here are the available df row and column labels:\n{all_labels}',
                instructions=dedent_triple_quote_str("""
                    The glossary keys should be a subset of the df labels.

                    Please revise the code changing either the glossary keys, or the df labels, accordingly.

                    As a reminder: you can also use the `note` argument to add information that is related to the
                    displayitem as a whole, rather than to a specific label.
                    """)
            )

    def _create_displayitem_caption_label_issue(self, issue: str):
        self._append_issue(
            category='Problem with displayitem caption',
            issue=issue,
            instructions=dedent_triple_quote_str("""
                Please revise the code making sure all displayitems are created with a caption.
                Use the arguments `caption` of `df_to_latex` or `df_to_figure`.
                Captions should be suitable for tables/figures of a scientific paper.
                In addition, you can add:
                - an optional note for further explanations (use the argument `note`)
                - a glossary mapping any abbreviated row/column labels to their definitions \t
                (use the argument `glossary` argument). 
                """)
        )

    def _check_caption_or_note(self, text: Optional[str], item_name: str = 'caption', is_required: bool = True):
        forbidden_starts: Tuple[str, ...] = ('Figure', 'Table')
        if text is None:
            if is_required:
                self._create_displayitem_caption_label_issue(
                    f'The {self.table_or_figure} does not have a {item_name}.')
            else:
                return
        else:
            for forbidden_start in forbidden_starts:
                if text.startswith(forbidden_start):
                    self._create_displayitem_caption_label_issue(
                        f'The {item_name} of the {self.table_or_figure} should not start with "{forbidden_start}".')
            if '...' in text:
                self._create_displayitem_caption_label_issue(
                    f'The {item_name} of the {self.table_or_figure} should not contain "..."')
            if re.search(pattern=r'<.*\>', string=text):
                self._create_displayitem_caption_label_issue(
                    f'The {item_name} of the {self.table_or_figure} should not contain "<...>"')

    def check_note(self):
        self._check_caption_or_note(self.note, item_name='note', is_required=False)

    def check_caption(self):
        self._check_caption_or_note(self.caption, item_name='caption', is_required=True)

    def check_note_is_different_than_caption(self):
        note, caption = self.note, self.caption
        if note is not None and caption is not None and (
                note.lower() in caption.lower() or caption.lower() in note.lower()):
            self._create_displayitem_caption_label_issue(
                f'The note of the {self.table_or_figure} should not be the same as the caption.\n'
                'Notes are meant to provide additional information, not to repeat the caption.')

    CHOICE_OF_CHECKS = BaseContentDfChecker.CHOICE_OF_CHECKS | {
        check_for_unallowed_characters_in_labels: True,
        check_for_abbreviations_not_in_glossary: True,
        check_for_glossary_labels_not_in_df: True,
        check_note: True,
        check_caption: True,
        check_note_is_different_than_caption: True,
    }


""" FILE CONTINUITY """


@dataclass
class ContinuityDfChecker(BaseContentDfChecker):
    DEFAULT_CATEGORY = 'File continuity'

    def check_for_file_continuity(self):
        if not isinstance(self.df, ListInfoDataFrame):
            self._append_issue(
                issue=f"You can only use the loaded `df` object (you can change the loaded df, but not replace it)",
            )
            return
        previous_filename = self.df.extra_info[-1][2]
        should_be_filename = previous_filename + '_formatted'
        if self.filename != should_be_filename:
            self._append_issue(
                issue=dedent_triple_quote_str(f"""
                    The file name of the loaded df was "{previous_filename}".
                    The current file name should be "{should_be_filename}" (instead of "{self.filename}").
                    """),
            )

    CHOICE_OF_CHECKS = BaseContentDfChecker.CHOICE_OF_CHECKS | {
        check_for_file_continuity: True,
    }


""" RUN CHECKERS """


def check_df_to_figure_analysis(df: pd.DataFrame, filename: str, kwargs) -> RunIssues:
    checkers = [
        FigureSyntaxDfChecker,
        FigureDfContentChecker,
    ]
    return create_and_run_chain_checker(checkers, df=df, filename=filename, kwargs=kwargs)[0]


def check_df_to_latex_analysis(df: pd.DataFrame, filename: str, kwargs) -> RunIssues:
    checkers = [
        TableSyntaxDfChecker,
        TableDfContentChecker,
    ]
    return create_and_run_chain_checker(checkers, df=df, filename=filename, kwargs=kwargs)[0]


def check_df_to_figure_displayitems(df: pd.DataFrame, filename: str, kwargs) -> RunIssues:
    checkers = [
        FigureSyntaxDfChecker,
        FigureDfContentChecker,
        ContinuityDfChecker,
        SecondFigureContentChecker,
        FigureCompilationDfContentChecker,
        AnnotationDfChecker,
    ]
    return create_and_run_chain_checker(checkers, df=df, filename=filename, kwargs=kwargs)[0]


def check_df_to_latex_displayitems(df: pd.DataFrame, filename: str, kwargs) -> RunIssues:
    checkers = [
        TableSyntaxDfChecker,
        TableDfContentChecker,
        ContinuityDfChecker,
        SecondTableContentChecker,
        TableCompilationDfContentChecker,
        AnnotationDfChecker,
    ]
    return create_and_run_chain_checker(checkers, df=df, filename=filename, kwargs=kwargs)[0]
