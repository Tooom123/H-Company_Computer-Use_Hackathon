"""Document context must reach H without fabricating an agent tool invocation."""
import threading
from types import SimpleNamespace

from hcs_agent.knowledge import DocAnswer, NoKnowledge, Source
from pilot.browser_backend import BrowserHBackend


class Knowledge:
    retrieval_method = 'local_markdown_bm25'

    def ask(self, query, software=None):
        return DocAnswer(query=query, answer='Read the receipt before concluding.',
                         sources=[Source(name='Guide', url='knowledge://guide/v1')])


def invoke(knowledge, *, stopped=False):
    backend = object.__new__(BrowserHBackend)
    backend.knowledge = knowledge
    backend._documentation_context = []
    captured = {}
    backend._perform = lambda method, args, kwargs: captured.update(args=args)
    bound = SimpleNamespace(request=SimpleNamespace(goal='Read the order', software='odoo'))
    stop = threading.Event()
    if stopped:
        stop.set()
    backend.run_attempt(bound, 'Allowed: read only', 1, lambda step: None, stop,
                        lambda answer: captured.update(fake_agent_lookup=True))
    return backend, captured


def test_context_reaches_actor_and_provenance_is_not_an_agent_lookup():
    backend, captured = invoke(Knowledge())
    assert 'Allowed: read only' in captured['args'][1]
    assert 'Read the receipt before concluding.' in captured['args'][1]
    assert 'knowledge://guide/v1' in captured['args'][1]
    assert 'not authorization' in captured['args'][1]
    assert 'fake_agent_lookup' not in captured
    assert backend._documentation_context[0]['purpose'] == 'automatic_context'
    assert backend._documentation_context[0]['document_answer']['query'] == 'Read the order'


def test_disabled_and_stopped_runs_do_not_inject_documentation():
    for knowledge, stopped in [(NoKnowledge(), False), (Knowledge(), True)]:
        backend, captured = invoke(knowledge, stopped=stopped)
        assert captured['args'][1] == 'Allowed: read only'
        assert backend._documentation_context == []


def test_optional_retrieval_failure_is_sanitized_and_does_not_prevent_execution():
    class Unavailable(Knowledge):
        def ask(self, *args, **kwargs):
            raise RuntimeError('private exception details')
    backend, captured = invoke(Unavailable())
    assert captured['args'][1] == 'Allowed: read only'
    assert backend._documentation_context == [
        {'purpose': 'automatic_context', 'attempt': 1, 'available': False,
         'status': 'retrieval_unavailable'}]
