import json

def analyze(path, label):
    with open(path, encoding='utf-8') as f:
        d = json.load(f)
    sms = d.get('sub_modules', [])
    total_g = sum(len(sm.get('groups',[])) for sm in sms)
    total_m = sum(len(g.get('value',[])) for sm in sms for g in sm.get('groups',[]))
    print(f"--- {label} ---")
    print(f"  sub_modules  : {len(sms)}")
    print(f"  total_groups : {total_g}")
    print(f"  total_metrics: {total_m}")
    print(f"  iterations/row: {len(sms)} SM x {total_g} G x {total_m} M")
    print()

analyze('utils/modules/product/reference_data/product_performance_json_file.json', 'PRODUCT')
analyze('utils/modules/esgrc/reference_data/esgrc_performance_json_file.json', 'ESGRC')
analyze('utils/modules/bspt/reference_data/bspt_performance_json_file.json', 'BSPT')
