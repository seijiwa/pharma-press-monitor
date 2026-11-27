"""Explicit security/issuer mappings. Never infer US identity from a foreign ticker."""
import re,unicodedata

ADR={'NOVN':'NVS','NOVOB':'NVO','SAN':'SNY','GRF':'GRFS',
     'ROP':'RHHBY','BAYN':'BAYRY','CSL':'CSLLY','FRE':'FSNUY',
     'LONN':'LZAGY','HLUN':'HLUYY','GALD':'GALDY','ZEAL':'ZLDPF'}
US=set('ABBV ALKS ALMS ALVO AMGN ARWR AZN BMRN BIIB BMY CAPR CGEM DNLI LLY ENTA ERAS EXEL GSK GILD HRMY HIMS IMNM IONS JAZZ JNJ KURA MRK NBIX ORKA PFE REGN RVMD SRPT SRRK GPCR SMMT SUPN TEVA RARE VERA VRTX VKTX'.split())
NAMES={'SUPN':('Supernus Pharmaceuticals','Supernus Inc'),'ROP':('Roche Holding','Roche Holdings'),'CSL':('CSL Limited','CSL Ltd'),
       'FRE':('Fresenius SE','Fresenius SE & Co'),'LONN':('Lonza Group',),
       'HLUN':('H Lundbeck','Lundbeck'),'GALD':('Galderma Group',),
       'NOVN':('Novartis',),'NOVOB':('Novo Nordisk',),'SAN':('Sanofi',),'GRF':('Grifols',),
       'BAYN':('Bayer AG',),'ZEAL':('Zealand Pharma',),
       'TEVA':('Teva Pharmaceutical Industries',),'LLY':('Eli Lilly',),
       'SMMT':('Summit Therapeutics',),'SRRK':('Scholar Rock',),'GSK':('GSK','GlaxoSmithKline')}
def canonical(value):
    return ' '.join(re.findall(r'[a-z0-9]+',unicodedata.normalize('NFKD',str(value)).lower()))
def matches_name(actual,expected):
    a=canonical(actual);e=canonical(expected)
    return bool(e) and (a==e or a.startswith(e+' '))
def resolve(company,tickers):
    t=company['ticker']
    symbol=ADR.get(t) or (t if t in US else None)
    if not symbol or symbol not in tickers:return None
    cik=tickers[symbol]
    if t=='SUPN' and cik not in (1356576,1625297):return None
    return {'sec_ticker':symbol,'cik':cik,'expected_names':NAMES.get(t,(company['name'],))}
def verify_identity(data,mapping):
    return (int(data['cik'])==mapping['cik'] and mapping['sec_ticker'] in [s.upper() for s in data['tickers']]
            and any(matches_name(data.get('name',''),n) for n in mapping['expected_names']))
