import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('source_audit',Path(__file__).resolve().parents[1]/'scripts/audit_manuscript_source.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class ManuscriptSourceTests(unittest.TestCase):
    def test_orcid_checksum_does_not_establish_ownership(self):
        self.assertTrue(module.orcid_checksum('0000-0002-1825-0097'))
        self.assertFalse(module.orcid_checksum('0000-0002-1825-0098'))
        row=module.scan('https://orcid.org/0000-0002-1825-0097')['orcids'][0]
        self.assertFalse(row['owner_verified'])

    def test_comments_not_counted_but_escaped_percent_preserved(self):
        result=module.scan('% \\begin{equation}\nValue 80\\%\n\\begin{equation} x=1 \\end{equation}')
        self.assertEqual(result['equation_environments'],1)

    def test_pending_author_details_and_adjacent_citations_detected(self):
        result=module.scan('AUTHOR CONFIRMATION REQUIRED \\cite{a} \\cite{b}')
        self.assertEqual({f['code'] for f in result['findings']},{'author_confirmation_pending','adjacent_citations'})
        self.assertFalse(result['submission_ready_certified'])

    def test_included_sources_are_not_silently_ignored(self):
        with self.assertRaises(ValueError):module.scan('\\input{chapter}')


if __name__=='__main__':unittest.main()
