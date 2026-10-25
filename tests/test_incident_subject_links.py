"""New incident articles need the linked venue/vehicle before generic city photos."""
from desk import writer


def test_florida_article_finds_named_venues_without_background_or_generic_links():
    raw = {'location': '[[Tallahassee]], [[Florida]]'}
    text = ("A shooting occurred near [[Florida A&M University]] in [[Tallahassee, Florida]].\n"
            "== Shooting ==\nIt followed a game at [[Bragg Memorial Stadium]].\n"
            "== Background ==\nA previous event happened at [[Example High School]].\n"
            "== Response ==\nStudents at the [[school]] were advised to avoid the area.")
    assert writer.incident_subject_links(raw, text) == ['Florida A&M University', 'Bragg Memorial Stadium']


def test_actual_transport_precedes_venues_and_places_without_unrelated_hospital():
    raw = {'line': '[[Karachi–Peshawar Line]]', 'operator': '[[Pakistan Railways]]',
           'trains': 'A [[passenger train]]', 'location': '[[Multan]]'}
    text = ('The [[Rehman Baba Express]] derailed near [[Sher Shah Junction railway station]]. '
            'Patients were taken to [[Nishtar Hospital]].')
    assert writer.incident_subject_links(raw, text) == [
        'Karachi–Peshawar Line', 'Pakistan Railways', 'Rehman Baba Express', 'Sher Shah Junction railway station']
