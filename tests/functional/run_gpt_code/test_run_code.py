import os
import time

import pytest

from data_to_paper.research_types.scientific_research.coding_steps import DictPickleContentOutputFileRequirement
from data_to_paper.research_types.scientific_research.utils_for_gpt_code.utils_modified_for_gpt_use.set_seed_for_sklearn_models import \
    sklearn_random_state_init_replacer
from data_to_paper.run_gpt_code.dynamic_code import RunCode, FailedRunningCode
from data_to_paper.run_gpt_code.exceptions import CodeUsesForbiddenFunctions, \
    CodeWriteForbiddenFile, CodeImportForbiddenModule, UnAllowedFilesCreated
from data_to_paper.run_gpt_code.overrides.contexts import OverrideStatisticsPackages
from data_to_paper.run_gpt_code.types import OutputFileRequirements
from data_to_paper.utils import dedent_triple_quote_str


def test_run_code_on_legit_code():
    code = dedent_triple_quote_str("""
        def f():
            return 'hello'
        """)
    run_code = RunCode()
    run_code.run(code)
    assert run_code._module.f() == 'hello'


def test_run_code_correctly_reports_exception():
    code = dedent_triple_quote_str("""
        # line 1
        # line 2
        raise Exception('error')
        # line 4
        """)
    error = RunCode().run(code)[4]
    assert isinstance(error, FailedRunningCode)
    assert error.exception.args[0] == 'error'
    linenos_lines, msg = error.get_lineno_line_message()
    assert linenos_lines == [(3, "raise Exception('error')")]


def test_run_code_raises_warning():
    code = dedent_triple_quote_str("""
        import warnings
        warnings.warn('be careful', UserWarning)
        """)
    error = RunCode(warnings_to_raise=[UserWarning]).run(code)[4]
    assert isinstance(error, FailedRunningCode)
    lineno_line, msg = error.get_lineno_line_message()
    assert msg == 'be careful'
    assert lineno_line == [(2, "warnings.warn('be careful', UserWarning)")]


def test_run_code_issues_warning():
    code = dedent_triple_quote_str("""
        import warnings
        warnings.warn('be careful', UserWarning)
        """)
    result, created_files, issues, contexts, e = RunCode(warnings_to_issue=[UserWarning]).run(code)
    assert e is None
    assert len(issues) == 1
    assert 'be careful' in issues[0].issue
    assert issues[0].linenos_and_lines == [(2, "warnings.warn('be careful', UserWarning)")]


def test_run_code_correctly_reports_exception_from_func():
    code = dedent_triple_quote_str("""
        def func():
            raise Exception('stupid error')
        func()
        """)
    error = RunCode().run(code)[4]
    assert isinstance(error, FailedRunningCode)
    assert error.exception.args[0] == 'stupid error'
    linenos_lines, msg = error.get_lineno_line_message()
    assert linenos_lines == [(3, 'func()'), (2, "raise Exception('stupid error')")]
    msg = error.get_traceback_message()
    assert 'func()' in msg
    assert "raise Exception('stupid error')" in msg
    assert 'stupid error' in msg


def test_run_code_timeout():
    code = dedent_triple_quote_str("""
        import time
        # line 2
        time.sleep(20)
        # line 4
        """)
    results = RunCode(timeout_sec=1).run(code)
    error = results[4]
    assert isinstance(error, FailedRunningCode)
    assert isinstance(error.exception, TimeoutError)
    lineno_lines, msg = error.get_lineno_line_message()
    assert lineno_lines == [(3, 'time.sleep(20)')]


@pytest.mark.parametrize("forbidden_call", ['input', 'exit', 'quit', 'eval'])
def test_run_code_forbidden_functions(forbidden_call):
    time.sleep(0.1)
    code = dedent_triple_quote_str("""
        a = 1
        {}()
        """).format(forbidden_call)
    error = RunCode().run(code)[4]
    assert isinstance(error, FailedRunningCode)
    assert isinstance(error.exception, CodeUsesForbiddenFunctions)
    lineno_lines, msg = error.get_lineno_line_message()
    assert lineno_lines == [(2, '{}()'.format(forbidden_call))]
    # TODO: some wierd bug - the message is not always the same:
    # assert forbidden_call in msg


def test_run_code_forbidden_function_print():
    code = dedent_triple_quote_str("""
        a = 1
        print(a)
        a = 2
        """)
    result, created_files, issues, contexts, error = RunCode().run(code)
    assert 'print' in issues[0].issue


@pytest.mark.parametrize("forbidden_import,module_name", [
    ('import os', 'os'),
    ('from os import path', 'os'),
    ('import os.path', 'os.path'),
    ('import sys', 'sys'),
    ('import matplotlib', 'matplotlib'),
    ('import matplotlib as mpl', 'matplotlib'),
    ('import matplotlib.pyplot as plt', 'matplotlib.pyplot'),
])
def test_run_code_forbidden_import(forbidden_import, module_name):
    code = dedent_triple_quote_str("""
        import scipy
        import numpy as np
        {}
        """).format(forbidden_import)
    error = RunCode().run(code)[4]
    assert isinstance(error, FailedRunningCode)
    assert isinstance(error.exception, CodeImportForbiddenModule)
    assert error.exception.module == module_name
    lineno_lines, msg = error.get_lineno_line_message()
    assert lineno_lines == [(3, forbidden_import)]


def test_run_code_forbidden_import_should_not_raise_on_allowed_packages():
    code = dedent_triple_quote_str("""
        import pandas as pd
        import numpy as np
        from scipy.stats import chi2_contingency
        """)
    RunCode().run(code)


def test_run_code_wrong_import():
    code = dedent_triple_quote_str("""
        from xxx import yyy
        """)
    error = RunCode().run(code)[4]
    assert isinstance(error, FailedRunningCode)
    assert error.exception.fromlist == ('yyy', )


code = dedent_triple_quote_str("""
    with open('test.txt', 'w') as f:
        f.write('hello')
    """)


def test_run_code_raises_on_unallowed_open_files(tmpdir):
    error = RunCode(allowed_open_write_files=[], run_folder=tmpdir).run(code)[4]
    assert isinstance(error, FailedRunningCode)
    assert isinstance(error.exception, CodeWriteForbiddenFile)
    linenos_lines, msg = error.get_lineno_line_message()
    assert linenos_lines == [(1, "with open('test.txt', 'w') as f:")]


def test_run_code_raises_on_unallowed_created_files(tmpdir):
    error = RunCode(allowed_open_write_files=None, run_folder=tmpdir).run(code)[4]
    assert isinstance(error, FailedRunningCode)
    assert isinstance(error.exception, UnAllowedFilesCreated)
    lineno_line, msg = error.get_lineno_line_message()
    assert lineno_line == []


def test_run_code_allows_allowed_files(tmpdir):
    os.chdir(tmpdir)
    RunCode(allowed_open_write_files=['test.txt'], output_file_requirements=None).run(code)


def test_run_code_that_creates_pvalues_using_f_oneway(tmpdir):
    code = dedent_triple_quote_str("""
        import pickle
        import pandas as pd 
        from scipy.stats import f_oneway
        all_mses = [[1, 2, 3], [4, 5, 6], [7, 8, 9], 
                    pd.Series([10, 11, 12, 13 ,14]), pd.Series([15, 16, 17, 18, 19]), pd.Series([20, 21, 22, 23, 24])]
        F, p = f_oneway(*all_mses)
        additional_results = {'f_score': F, 'p_value': p}
        with open('additional_results.pkl', 'wb') as f:
            pickle.dump(additional_results, f)
        """)
    with OverrideStatisticsPackages():
        error = RunCode(run_folder=tmpdir,
                        allowed_open_write_files=None,
                        output_file_requirements=OutputFileRequirements(
                            (DictPickleContentOutputFileRequirement('additional_results.pkl', 1),)),).run(code)[4]
        if error is not None:
            raise error
        assert os.path.exists(tmpdir / 'additional_results.pkl')
        import pickle
        p_value = pickle.load(open(tmpdir / 'additional_results.pkl', 'rb'))['p_value']
        assert p_value.created_by == 'f_oneway'


def test_run_code_with_sklearn_class_with_no_random_state_defined():
    code = """
from sklearn.linear_model import ElasticNet
from sklearn.ensemble import RandomForestRegressor
from sklearn.neural_network import MLPRegressor
# initialize models without setting random_state
models = {'Random Forest': RandomForestRegressor(), 'Elastic Net': ElasticNet(), 'Neural network': MLPRegressor()}
# check if models are initialized with `random_state=0` by using the replacer we created
for model in models.keys():
    if hasattr(models[model], 'random_state'):
        assert models[model].random_state == 0, f'{model} is not initialized with random_state=0'
"""
    error = RunCode(additional_contexts={'SklearnRandomSeedInitReplacer': sklearn_random_state_init_replacer()}).run(code)[4]
    if error is not None:
        raise error
