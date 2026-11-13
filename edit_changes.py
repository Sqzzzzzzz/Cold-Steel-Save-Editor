"""Read-only quantity changes relative to the opened file; no file IO."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ItemChange:
    item_id: int
    before: int
    after: int

    @property
    def kind(self):
        return 'added' if self.before==0 else 'removed' if self.after==0 else 'modified'


class EditChanges:
    def __init__(self):
        self._original=None
        self.before={}
        self.current={}
        self.changes={}

    def refresh(self,save):
        if save is None:
            self._original=None;self.before={};self.current={};self.changes={}
            return
        # The engine retains immutable original bytes across undo/reset. Read
        # them once per baseline; never change the engine's saved snapshots.
        if self._original is not save.original_items:
            self._original=save.original_items
            self.before=save.original_items
        if self.current is save.quantities:
            return
        self.current=save.quantities
        self.changes={i:ItemChange(i,self.before.get(i,0),self.current.get(i,0))
                      for i in sorted(self.before.keys()|self.current.keys())
                      if self.before.get(i,0)!=self.current.get(i,0)}

    def counts(self):
        return {kind:sum(change.kind==kind for change in self.changes.values())
                for kind in ('added','removed','modified')}
