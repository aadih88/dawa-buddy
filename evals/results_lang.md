# Hindi / Kannada explainer: live check

Models: hi ['nvidia/Nemotron-3-Ultra-550b-a55b', 'nvidia/nemotron-3-super-120b-a12b'], kn ['nvidia/Nemotron-3-Ultra-550b-a55b', 'nvidia/Nemotron-3-Ultra-550b-a55b', 'nvidia/Nemotron-3-Ultra-550b-a55b']

| Language | Case | Medicines | Outcome | Target-script / stray-script letters | Latency |
|---|---|---|---|---|---|
| hi | three common tablets | 3 | accepted | 506 / 0 | 1.7s |
| hi | heart and diabetes | 4 | accepted | 492 / 0 | 1.8s |
| kn | three common tablets | 3 | accepted | 573 / 0 | 2.4s |
| kn | heart and diabetes | 4 | accepted | 647 / 0 | 20.3s |

Machine-checked for script only. A native speaker has not yet reviewed the wording.
Kannada AI text is switched off for users by default: a real run passed this script check yet contained place names and 'Friday' as side effects.
