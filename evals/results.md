# Eval results

Mode: nebius: nvidia/Nemotron-3_5-Lightning  |  Cases: 24

| Metric | Precision | Recall | F1 |
|---|---|---|---|
| Medicine extraction (name, frequency, days) | 1.00 | 1.00 | 1.00 |
| Safety flags | 1.00 | 1.00 | 1.00 |

Hallucinated medicines (not in source text): 0
Median latency: 1.33s

| Case | Meds correct | Flags raised | Flags expected |
|---|---|---|---|
| fever_basic | 1/1 | - | - |
| cold_course | 2/2 | - | - |
| double_paracetamol | 2/2 | Same ingredient twice | Same ingredient twice |
| warfarin_nsaid | 2/2 | Bleeding risk | Bleeding risk |
| warfarin_aspirin | 2/2 | Bleeding risk | Bleeding risk |
| two_nsaids | 2/2 | Two painkillers of the same type | Two painkillers of the same type |
| diabetes_bp | 3/3 | - | - |
| statin_macrolide | 2/2 | Muscle damage risk | Muscle damage risk |
| nitrate_sildenafil | 2/2 | Dangerous blood pressure drop | Dangerous blood pressure drop |
| missing_duration | 1/1 | Something is not written | Something is not written |
| paracetamol_overdose | 2/2 | Paracetamol above 4 g a day, Same ingredient twice | Paracetamol above 4 g a day, Same ingredient twice |
| week_duration | 1/1 | - | - |
| messy_words | 1/1 | - | - |
| messy_sentence | 2/2 | - | - |
| messy_abbrev | 2/2 | - | - |
| messy_interaction | 2/2 | Bleeding risk | Bleeding risk |
| ho_twice_weeks | 1/1 | - | - |
| ho_once_night | 1/1 | - | - |
| ho_od_before_breakfast | 1/1 | - | - |
| ho_sos | 1/1 | - | - |
| ho_bedtime_months | 1/1 | - | - |
| ho_hs_short | 1/1 | - | - |
| ho_two_in_one_line | 2/2 | - | - |
| ho_numbered_mixed | 2/2 | - | - |
