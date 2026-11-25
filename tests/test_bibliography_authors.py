import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('registry',Path(__file__).resolve().parents[1]/'scripts/audit_bibliography_registry.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class AuthorAuditTests(unittest.TestCase):
    def test_wrong_given_name_detected_even_when_family_matches(self):
        self.assertIn('author_full_name_or_order_differs',module.author_issues('Chen, Andrea Madotto',['Chen'],['Delong Chen']))

    def test_extra_authors_detected(self):
        self.assertIn('author_count_differs',module.author_issues('Ji, Ziwei and Lee, Nayeon and Other, Person',['Ji','Lee'],['Ziwei Ji','Nayeon Lee']))

    def test_bibtex_name_order_is_allowed_but_author_order_is_checked(self):
        self.assertEqual(module.author_issues('Jeong, Yuna and Kim, Eunhui',['Jeong','Kim'],['Yuna Jeong','Eunhui Kim']),[])
        self.assertIn('author_full_name_or_order_differs',module.author_issues('Kim, Eunhui and Jeong, Yuna',['Jeong','Kim'],['Yuna Jeong','Eunhui Kim']))

    def test_missing_given_names_do_not_certify_full_names(self):
        issues=module.author_issues('Chen, Andrea',['Chen'],[''])
        self.assertNotIn('author_full_name_or_order_differs',issues)

    def test_truncated_list_requires_review(self):
        self.assertIn('truncated_author_list_requires_review',module.author_issues('Ji, Ziwei and others',['Ji'],['Ziwei Ji']))


if __name__=='__main__':unittest.main()
