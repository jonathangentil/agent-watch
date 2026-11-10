"""Names derived from declared assignments, never from model activity."""
import re

from ._io import safe_text

ROLE_NAMES = {'planner': 'Planner', 'developer': 'Developer', 'reviewer': 'Reviewer', 'qa': 'QA'}
ALIASES = {'planner': 'planner', 'planejador': 'planner',
           'developer': 'developer', 'dev': 'developer', 'desenvolvedor': 'developer', 'implementer': 'developer',
           'reviewer': 'reviewer', 'review': 'reviewer', 'rev': 'reviewer', 'rerev': 'reviewer', 'revisor': 'reviewer',
           'qa': 'qa', 'tester': 'qa'}
_ROLES = '|'.join(ALIASES)
_ASSIGNMENT = re.compile(
    r'(?im)^\s*(?:#{1,6}\s*)?(?:(?:role|função|papel)\s*:\s*|'
    r'(?:you are|act as|você é|voce e|atue como)\s+(?:(?:a|an|um|uma|o)\s+)?(?:senior\s+)?|'
    r'pipeline contract\s*\()(' + _ROLES + r')\b'
)


def identify_role(declared='', task='', identifier=''):
    role = ALIASES.get(safe_text(declared).strip().lower())
    if role:
        return role, 'função declarada nos metadados'
    assigned = {ALIASES[m.lower()] for m in _ASSIGNMENT.findall(task[:10000])}
    if len(assigned) == 1:
        return assigned.pop(), 'atribuição explícita na tarefa'
    tokens = re.split(r'[-_./\s]+', identifier.lower())
    roles = {ALIASES[token] for token in tokens if token in ALIASES}
    if len(roles) == 1:
        return roles.pop(), 'função no identificador registrado'
    return None, ''


def task_summary(task):
    task = task.split('\n\nRuntime contract:', 1)[0]
    text = ' '.join(task.split())
    return text[:277] + '…' if len(text) > 280 else text
