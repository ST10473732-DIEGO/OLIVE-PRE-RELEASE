"""Durable remote-mutation intent; never replay an interrupted IMAP command."""
from contextlib import contextmanager
from .store import WRITE_GUARD, Conflict


@contextmanager
def remote_outcome(store, connection_id, action, target):
    with store.transaction() as db:
        pending = db.execute("SELECT body FROM records WHERE kind='annotation' AND json_extract(body,'$.type')='remote_operation' AND json_extract(body,'$.connection_id')=? AND json_extract(body,'$.target')=? AND json_extract(body,'$.state')='pending'", (connection_id, target)).fetchone()
        if pending:
            raise Conflict('A remote change is already pending for this target')
        operation = store.save(db, 'annotation', dict(type='remote_operation', connection_id=connection_id,
            action=action, target=target, state='pending'))
    outcome = {'state': 'outcome_uncertain'}
    first_error = None
    try:
        yield outcome
        outcome['state'] = 'confirmed'
    except Exception as error:
        first_error = error
        outcome['category'] = type(error).__name__
        raise RuntimeError('Remote change outcome uncertain; refresh the mailbox before deciding on another action. Operation '+operation['id']) from error
    finally:
        # An operation may have reached the server. Cancellation/Deny must not
        # erase that fact; this writes only its outcome, never another command.
        token = WRITE_GUARD.set(None)
        try:
            try:
                with store.transaction() as db:
                    body = store.body(operation); body.update(outcome)
                    store.save(db, 'annotation', body, operation['id'], operation['revision'])
            except Exception as persistence_error:
                if first_error is None:raise
                first_error.add_note('Outcome persistence also failed: '+type(persistence_error).__name__)
        finally:
            WRITE_GUARD.reset(token)
