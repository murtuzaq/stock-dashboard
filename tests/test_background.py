"""BackgroundLoader: results and failures are handed to the GUI thread via `post`, possibly later."""
import threading

from core.background import BackgroundLoader


def deferred_loader():
    """A loader whose posted callbacks wait until the test runs them, like a real GUI event queue."""
    queue = []
    return BackgroundLoader(post=queue.append, threaded=False), queue


def test_result_is_posted_not_called_directly():
    loader, queue = deferred_loader()
    results = []
    loader.run(lambda: 42, results.append)
    assert results == [] and len(queue) == 1
    queue.pop()()
    assert results == [42]


def test_failure_is_posted_with_the_error_even_after_the_except_block_ended():
    loader, queue = deferred_loader()
    errors = []

    def boom():
        raise OSError('offline')

    loader.run(boom, lambda result: errors.append('done called'), errors.append)
    queue.pop()()  # runs after _execute returned: the exception variable must still be reachable
    assert len(errors) == 1 and isinstance(errors[0], OSError)


def test_failure_without_a_handler_is_swallowed_and_logged(caplog):
    loader, queue = deferred_loader()
    loader.run(lambda: 1 / 0, lambda result: None)
    assert queue == [] and 'Background work failed' in caplog.text


def test_threaded_work_runs_off_the_calling_thread():
    done = threading.Event()
    seen = {}

    def work():
        seen['worker'] = threading.current_thread()
        return 'ok'

    def post(call):
        call()
        done.set()

    BackgroundLoader(post=post).run(work, lambda result: seen.update(result=result))
    assert done.wait(5)
    assert seen['result'] == 'ok' and seen['worker'] is not threading.current_thread()


def test_immediate_loader_runs_everything_inline():
    results = []
    BackgroundLoader.immediate().run(lambda: 'x', results.append)
    assert results == ['x']
