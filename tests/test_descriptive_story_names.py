"""Regression from the sister desk: Clashes must not replace a reported city."""
from datetime import datetime, timedelta, timezone

from desk import outlets


NOW = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)


def rows(titles):
    sources = {o['key']: o for o in outlets.OUTLETS}
    keys = ['france24', 'bbc-world', 'thehindu']
    return [{'title': title, 'url': f'https://example.org/{key}',
             'outlet': sources[key]['name'], 'owner': sources[key]['owner'],
             'group': sources[key]['group'], 'lang': 'en', 'geo': 'world',
             'at': (NOW - timedelta(hours=hours)).isoformat(), 'summary': ''}
            for key, title, hours in zip(keys, titles, [3, 1, 4])]


def test_title_case_event_word_keeps_city_and_independent_owners():
    items = rows([
        'France: Clashes erupt as protests sweep across cities',
        'More than 1000 arrested as protesters clash with police in Paris as demonstrations turn hostile across France',
        'Clashes flare at Paris protests as more than 400,000 march across France'])
    got = outlets.stories(items, NOW)
    assert len(got) == 1 and got[0]['name'] == 'Paris'
    assert len(got[0]['owners']) == 3


def test_only_generic_words_leave_story_unidentified():
    assert outlets.stories(rows([
        'France: Clashes erupt as protests sweep across cities',
        'France: Clashes erupt across cities as protests continue',
        'Clashes erupt across France cities as protests continue']), NOW) == []
