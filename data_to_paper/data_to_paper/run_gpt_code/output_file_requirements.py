from __future__ import annotations
import os
import pickle
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Optional, Any, List, Tuple, Iterable, Dict

from data_to_paper.env import MAX_SENSIBLE_OUTPUT_SIZE_TOKENS, NUM_DIGITS_FOR_FLOATS
from data_to_paper.servers.chatgpt import count_number_of_tokens_in_message
from data_to_paper.servers.model_engine import ModelEngine
from data_to_paper.utils import dedent_triple_quote_str
from data_to_paper.utils.text_extractors import extract_to_nearest_newline
from data_to_paper.utils.text_numeric_formatting import round_floats
from data_to_paper.utils.ref_numeric_values import create_hypertargets_to_numeric_values

from .overrides.pvalue import OnStr, OnStrPValue
from .run_issues import CodeProblem, RunIssue


EXTS_TO_LABELS = {
    '.tex': 'latex',
    '.txt': 'output',
    '.csv': 'csv',
}


@dataclass(frozen=True)
class OutputFileRequirement:
    filename: str
    minimal_count: int
    should_keep_file: bool = NotImplemented

    def is_wildcard(self):
        return '*' in self.filename or '?' in self.filename

    def matches(self, filename: str):
        return fnmatch(filename, self.filename)

    def delete_if_needed(self, file_path: str):
        """
        Delete the file if needed.
        """
        if not self.should_keep_file:
            os.remove(file_path)

    def get_content(self, file_path: str) -> Optional[str]:
        """
        Return the content of the file.
        If data file, return None.
        """
        return None

    def get_content_and_delete_if_needed(self, file_path: str) -> str:
        """
        Return the content of the file, and delete it if needed.
        """
        content = self.get_content(file_path)
        self.delete_if_needed(file_path)
        return content


@dataclass(frozen=True)
class DataOutputFileRequirement(OutputFileRequirement):
    minimal_count: int = 0
    should_keep_file: bool = True


@dataclass(frozen=True)
class BaseContentOutputFileRequirement(OutputFileRequirement):
    should_keep_file: bool = NotImplemented
    minimal_count: int = 1
    hypertarget_prefixes: Optional[Tuple[str]] = None

    def get_content(self, file_path: str) -> str:
        """
        Return the content of the file.
        """
        with open(file_path, 'r') as file:
            return file.read()

    def get_issues_for_output_file_content(self, filename: str, content: Any) -> List[RunIssue]:
        """
        Check the output and return a list of issues.
        """
        return []

    def get_pretty_content(self, content: Any, filename: str = None, pvalue_on_str: Optional[OnStr] = None) -> str:
        with OnStrPValue(pvalue_on_str):
            content = str(content)
        if filename is not None:
            label = EXTS_TO_LABELS.get(Path(filename).suffix, 'output')
            return f'"{filename}":\n```{label}\n{content}\n```\n'
        return content


@dataclass(frozen=True)
class PickleContentOutputFileRequirement(BaseContentOutputFileRequirement):
    should_keep_file: bool = True

    def get_content(self, file_path: str) -> Any:
        """
        Return the content of the file.
        """
        with open(file_path, 'rb') as file:
            return pickle.load(file)


@dataclass(frozen=True)
class TextContentOutputFileRequirement(BaseContentOutputFileRequirement):
    should_keep_file: bool = False
    max_tokens: Optional[int] = MAX_SENSIBLE_OUTPUT_SIZE_TOKENS.val

    def get_issues_for_output_file_content(self, filename: str, content: str) -> List[RunIssue]:
        issues = super().get_issues_for_output_file_content(filename, content)

        if len(content.strip()) == 0:
            # The output file is empty.
            issues.append(RunIssue(
                category='Output file content',
                item=filename,
                issue=f'The code created the output file "{filename}", but the file is just empty!',
                instructions="Please revise the code to make sure it correctly writes to the output file.",
                code_problem=CodeProblem.OutputFileContentLevelA,
            ))

        if self.max_tokens is not None \
                and count_number_of_tokens_in_message(content, max(ModelEngine)) > self.max_tokens:
            # Created output file is too large.
            issues.append(RunIssue(
                category='Output file content',
                item=filename,
                issue=dedent_triple_quote_str("""
                    The code created the output file "{}", but the file is too long!

                    Here, for context, is the beginning of the output:
                    ```output
                    {}
                    ```
                    """).format(filename, extract_to_nearest_newline(content, self.max_tokens)),
                instructions="Only sensible-length output should be written to the file.",
                code_problem=CodeProblem.OutputFileContentLevelC,
            ))

        return issues


@dataclass(frozen=True)
class NumericTextContentOutputFileRequirement(BaseContentOutputFileRequirement):
    target_precision: int = NUM_DIGITS_FOR_FLOATS
    source_precision: int = 10

    def get_pretty_content(self, content: Any, filename: str = None, pvalue_on_str: Optional[OnStr] = None) -> str:
        content = super().get_pretty_content(content, filename, pvalue_on_str)
        return round_floats(content, self.target_precision, self.source_precision)


class OutputFileRequirements(Tuple[OutputFileRequirement]):

    def get_all_allowed_created_filenames(self) -> Tuple[str]:
        return tuple(requirement.filename for requirement in self)

    def get_single_content_file(self) -> Optional[str]:
        content_file_requirements = [
            req for req in self
            if isinstance(req, BaseContentOutputFileRequirement) and not req.is_wildcard() and req.minimal_count == 1]
        if len(content_file_requirements) != 1:
            return None
        return content_file_requirements[0].filename

    def _get_requirements_to_output_files_and_unmatched_files(
            self, created_files: Iterable[str]) -> Tuple[Dict[OutputFileRequirement, List[str]], List[str]]:
        """
        Return:
            - a dictionary mapping each requirement to a dictionary mapping each output file to its content.
            - a list of files that were not matched to any requirement.
        """
        requirements_to_output_files = {requirement: [] for requirement in self}
        unmatched_files = []
        for created_file in created_files:
            for requirement in self:
                if requirement.matches(created_file):
                    requirements_to_output_files[requirement].append(created_file)
                    break
            else:
                unmatched_files.append(created_file)
        return requirements_to_output_files, unmatched_files

    def get_requirements_to_output_files(
            self, created_files: Iterable[str]) -> Dict[OutputFileRequirement, List[str]]:
        return self._get_requirements_to_output_files_and_unmatched_files(created_files)[0]

    def get_unmatched_files(self, created_files: Iterable[str]) -> List[str]:
        return self._get_requirements_to_output_files_and_unmatched_files(created_files)[1]

    def convert_to_output_file_requirements_with_content(self, created_files: Iterable[str],
                                                         run_folder) -> OutputFileRequirementsWithContent:
        """
        Returns an OutputFileRequirementsWithContent, which is a dictionary mapping each requirement to
        a dictionary mapping each output file to its content.
        """
        requirements_to_files = self.get_requirements_to_output_files(sorted(created_files))
        requirements_to_files_to_content = \
            {requirement: {
                output_file: requirement.get_content_and_delete_if_needed(
                    file_path=run_folder / output_file if run_folder else output_file)
                for output_file in files
            } for requirement, files in requirements_to_files.items()}
        return OutputFileRequirementsWithContent(requirements_to_files_to_content)


class OutputFileRequirementsWithContent(Dict[OutputFileRequirement, Dict[str, Any]]):
    """
    Should behave like a dictionary mapping each requirement to a dictionary mapping each output file to its content.
    """

    def convert_to_output_file_requirements(self) -> OutputFileRequirements:
        return OutputFileRequirements(self.keys())

    def get_single_content_file(self) -> Optional[str]:
        return self.convert_to_output_file_requirements().get_single_content_file()

    def get_all_created_files(self) -> List[str]:
        """
        Return the names of all the files created by the run.
        """
        return [filename for filenames_to_contents in self.values() for filename in filenames_to_contents.keys()]

    def get_created_content_files(self, match_filename: str = '*') -> List[str]:
        """
        Return the names of the files created by the run, for which we collected the content.
        """
        return [filename for requirement, files_to_contents in self.items()
                for filename in files_to_contents.keys()
                if isinstance(requirement, BaseContentOutputFileRequirement) and fnmatch(filename, match_filename)]

    def _get_created_content_files_to_contents(self, is_pretty: bool = True, pvalue_on_str: Optional[OnStr] = None,
                                               should_hypertarget: bool = False,
                                               match_filename: str = '*', is_block: bool = False) -> Dict[str, Any]:
        """
        Return the names of the files created by the run, and their content, formatted for display if needed.
        """
        # same code but with a normal for loop
        result = {}
        for requirement, files_to_contents in self.items():
            for num_file, (filename, content) in enumerate(files_to_contents.items()):
                if isinstance(requirement, BaseContentOutputFileRequirement) and fnmatch(filename, match_filename):
                    if is_pretty:
                        content = requirement.get_pretty_content(
                            content=content,
                            filename=filename if is_block else None,
                            pvalue_on_str=pvalue_on_str,
                        )
                    if should_hypertarget and requirement.hypertarget_prefixes:
                        content, _ = create_hypertargets_to_numeric_values(
                            content, prefix=requirement.hypertarget_prefixes[num_file])
                    result[filename] = content
        return result

    def get_created_content_files_to_pretty_contents(self,
                                                     pvalue_on_str: Optional[OnStr] = None,
                                                     should_hypertarget: bool = False,
                                                     match_filename: str = '*',
                                                     is_block: bool = False) -> Dict[str, str]:
        """
        Return the names of the files created by the run, and their content formatted for display.
        """
        return self._get_created_content_files_to_contents(is_pretty=True, pvalue_on_str=pvalue_on_str,
                                                           should_hypertarget=should_hypertarget,
                                                           match_filename=match_filename, is_block=is_block)

    def get_created_content_files_to_contents(self, match_filename: str = '*') -> Dict[str, Any]:
        """
        Return the names of the files created by the run, and their content.
        """
        return self._get_created_content_files_to_contents(is_pretty=False, match_filename=match_filename)

    def get_created_content_files_description(self, match_filename: str = '*', pvalue_on_str: Optional[OnStr] = None):
        files_to_contents = self.get_created_content_files_to_pretty_contents(pvalue_on_str=pvalue_on_str,
                                                                              match_filename=match_filename,
                                                                              is_block=True)
        return '\n\n'.join(files_to_contents.values())

    def get_single_output(self, is_pretty: bool = True, pvalue_on_str: Optional[OnStr] = None) -> Optional[str]:
        """
        Return the output of the run, if it is a single content file.
        """
        single_content_filename = self.get_single_content_file()
        if single_content_filename is None:
            return None
        return self._get_created_content_files_to_contents(
            is_pretty=is_pretty, pvalue_on_str=pvalue_on_str)[single_content_filename]

    def get_created_data_files(self, match_filename: str = '*') -> List[str]:
        """
        Return the names of the files created by the run, and which were kept, not deleted.
        """
        return [filename for requirement, files_to_contents in self.items()
                for filename in files_to_contents.keys() if
                requirement.should_keep_file and fnmatch(filename, match_filename)]

    def delete_all_created_files(self, run_folder: Optional[Path] = None):
        """
        Delete all the files that were created by the run, and which were kept, not deleted.
        """
        for filename in self.get_created_data_files():
            os.remove(run_folder / filename if run_folder else filename)
