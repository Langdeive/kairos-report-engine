import pytest

from kairos_report.errors import TutoryContractChanged
from kairos_report.tutory.parser import parse_question_report

EMPTY = '''
<div class="main-numbers"><h3></h3></div>
<div class="main-numbers"><h3></h3></div>
<div class="main-numbers"><h3>0%</h3></div>
<table id="tabela_questoes"><tbody></tbody></table>
<script>
var chartQuestoesDia = new Chart(el, {
 data: {labels: [], datasets: [
 {label: 'questões corretas', data: []},
 {label: 'questões erradas', data: []}]}});
var chartBolhaQuestoes = new Chart(el2, {data: {datasets: []}});
</script>
'''


def test_blank_totals_with_explicit_empty_charts_are_no_questions():
    result = parse_question_report(EMPTY)
    assert result.total == result.correct == result.wrong == 0
    assert result.weekly == result.disciplines == result.topics == []


@pytest.mark.parametrize('source', [
    EMPTY.replace('0%', '50%'),
    EMPTY.replace('labels: []', 'labels: ["semana"]'),
    EMPTY.replace('<table id="tabela_questoes"><tbody></tbody></table>', ''),
    EMPTY.replace('datasets: []', 'datasets: [{label: "unexpected", data: [1]}]'),
    EMPTY.replace('<h3></h3>', '<h3>1</h3>', 1),
    '<html>unavailable</html>',
])
def test_incomplete_or_conflicting_reports_are_not_silently_zero(source):
    with pytest.raises(TutoryContractChanged):
        parse_question_report(source)
