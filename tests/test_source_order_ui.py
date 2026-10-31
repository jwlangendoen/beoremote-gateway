"""Exercise the browser's local draft model without contacting a TV or HA."""
from pathlib import Path
import shutil
import subprocess
import unittest


class LocalOrderTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is needed for the browser draft model check")
    def test_draft_moves_cancellation_and_uncertain_write_reconciliation(self):
        html = (Path(__file__).resolve().parents[1] / "beoremote_gateway/gateway/setup.html").read_text()
        model = html.split("// source-order-model:start\n", 1)[1].split("// source-order-model:end", 1)[0]
        checks = r"""
const assert = require('node:assert/strict');
const helper = {revision:'r1',catalog:[
  {id:'console',source_list:'tv'},{id:'player',source_list:'tv'},{id:'shortcut',source_list:'tv'},
  {id:'radio',source_list:'music'},{id:'music',source_list:'music'}]};
const draft = new SourceOrderDraft('tv-a',helper,'tv');
assert.equal(draft.dirty,false);
assert.equal(draft.move('console',-1),false);
assert.equal(draft.move('radio',-1),false);
assert.equal(draft.move('shortcut',1),false);
assert.equal(draft.move('console',2),false);
assert.equal(draft.move('shortcut',-1),true);
assert.equal(draft.move('shortcut',-1),true);
assert.equal(draft.dirty,true);
assert.deepEqual(draft.ids,['shortcut','console','player']);
assert.deepEqual(helper.catalog.map(row=>row.id),['console','player','shortcut','radio','music']);
draft.move('shortcut',1);draft.move('shortcut',1);
assert.equal(draft.dirty,false); // Moving back to baseline is no change to save.
draft.move('player',-1);draft.needsRefresh=true;
assert.equal(draft.move('player',1),false); // Do not edit while write outcome is unknown.
assert.equal(draft.reconcile('tv-a',structuredClone(helper)),'retained');
assert.equal(draft.needsRefresh,false);
const committed={revision:'r2',catalog:[helper.catalog[1],helper.catalog[0],...helper.catalog.slice(2)]};
assert.equal(draft.reconcile('tv-a',committed),'saved'); // Lost reply after a committed write.
assert.equal(draft.reconcile('tv-b',committed),'changed'); // Never accept another TV's matching order.
assert.equal(draft.reconcile('tv-a',{...helper,revision:'r2'}),'changed');
assert.equal(draft.reconcile('tv-a',{...helper,catalog:helper.catalog.slice(0,-1)}),'changed');
const music=new SourceOrderDraft('tv-a',helper,'music');
music.move('music',-1);assert.deepEqual(music.ids,['music','radio']);
assert.deepEqual(draft.original,['console','player','shortcut']);
// Discarding the local object has never mutated the last confirmed helper snapshot.
assert.equal(helper.revision,'r1');assert.equal(helper.catalog[0].id,'console');
"""
        result = subprocess.run([shutil.which("node"), "-e", model + checks], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
