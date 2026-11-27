from pharma71_unified.official_fallback import parse_rss,parse_lundbeck,update_original_state,collect_fallback

def test_rss_requires_explicit_date_and_https():
    raw=b'<rss><channel><item><title>Official update</title><link>https://example.com/release</link><pubDate>Fri, 27 Nov 2026 08:00:00 +0900</pubDate></item><item><title>Missing date</title><link>https://example.com/other</link></item><item><title>Bad link</title><link>http://example.com/unsafe</link></item></channel></rss>'
    rows=parse_rss(raw)
    assert len(rows)==2 and rows[0]['listing_date']=='2026-11-27' and rows[1]['listing_date'] is None

def test_lundbeck_only_english_rows_and_explicit_publication_date():
    rows=parse_lundbeck(b'{"items":[{"language":"en","title":"Official release","url":"https://www.lundbeck.com/news/test","publishDate":"2026-11-20"},{"language":"da","title":"Other","url":"https://www.lundbeck.com/news/other","publishDate":"2026-11-21"}]}')
    assert len(rows)==1 and rows[0]['listing_date']=='2026-11-20'

def test_unverified_period_cannot_advance_baseline():
    prior={'companies':{'TEST':{'last_verified_success_jst':'2026-11-25T05:30:00+09:00'}}}
    state={'companies':{'TEST':{'last_verified_success_jst':'2026-11-27T05:30:00+09:00'}}}
    entry={'ticker':'TEST','status':'未確認','primary_releases':[{'original_confirmed':True,'url':'https://example.com/release','published_date':'2026-11-27'}]}
    update_original_state([entry],state,prior)
    assert state['companies']['TEST']['last_verified_success_jst']==prior['companies']['TEST']['last_verified_success_jst']
    assert 'https://example.com/release' in state['companies']['TEST']['seen_verified_urls']

def test_unregistered_feed_is_not_requested(tmp_path):
    class NoNetwork:
        def get(self,*a,**kw):raise AssertionError('unexpected request')
    e={'ticker':'TEST','status':'未確認','alternative_attempts':[]}
    c={'legacy_feed_url':'https://unrelated.example/rss','official_indexes':['https://official.example/news']}
    collect_fallback(e,c,None,tmp_path,session=NoNetwork())
    assert e['alternative_attempts']==[]
