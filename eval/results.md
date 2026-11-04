# Results

<!-- BEGIN phase3-baseline -->
## Phase 3 baseline: keyword search (BM25), no AI

- Documents in one index: boaters_guide.pdf, coast_pilot4_ch1.pdf, nav_rules.pdf (2149 pieces)
- Threshold `BASELINE_MIN_SCORE` = **11.5** (sweep recommends 11.5; rule below)
- Reading + chunking the PDFs: 24.4 s (once, at upload). Average search time per question: **1.8 ms**

| Measure | Result |
|---|---|
| Right doc + page, top 1 | 19/29 (66%) |
| Right doc + page, top 3 | 24/29 (83%) |
| Exact answer in top-1 piece (all numbers + key words) | 15/29 (52%) |
| Traps correctly "Not in this document" | 7/8 (88%) |
| Correct, other source: other doc/page, but the top-1 piece contains the source quote | 0 |
| **Wrong: answer shown is not supported** (must be 0 in Phase 4) | **6** |
| **Traps answered** (also wrong) | **1** |
| Missed: real question but said "Not in this document" | 4 |

Compare rows count as right page if the top piece is on either of their two pages. "Exact answer" is strict: a compare answer needs both pages, so it cannot be in one piece. "Right doc + page" stays strict; an answer from another doc or page counts as "correct, other source" only if its top-1 piece contains the row's source quote (normalised; compare rows: either quote). Every other answer from a wrong page is "wrong".

#### Per document

| Document | Questions | Right page top 1 | Right page top 3 | Exact answer top 1 | Correct, other source | Wrong | Missed |
|---|---|---|---|---|---|---|---|
| boaters_guide.pdf | 8 | 5/8 (62%) | 7/8 (88%) | 5/8 (62%) | 0 | 2 | 1 |
| coast_pilot4_ch1.pdf | 8 | 5/8 (62%) | 7/8 (88%) | 5/8 (62%) | 0 | 0 | 3 |
| nav_rules.pdf | 13 | 9/13 (69%) | 10/13 (77%) | 5/13 (38%) | 0 | 4 | 0 |

#### Per type

| Type | Questions | Right page top 1 | Right page top 3 | Exact answer top 1 | Correct, other source | Wrong | Missed |
|---|---|---|---|---|---|---|---|
| annex | 2 | 2/2 (100%) | 2/2 (100%) | 1/2 (50%) | 0 | 0 | 0 |
| compare | 3 | 2/3 (67%) | 2/3 (67%) | 0/3 (0%) | 0 | 1 | 0 |
| fact | 9 | 7/9 (78%) | 9/9 (100%) | 7/9 (78%) | 0 | 1 | 1 |
| number | 9 | 6/9 (67%) | 7/9 (78%) | 5/9 (56%) | 0 | 2 | 1 |
| paraphrase | 6 | 2/6 (33%) | 4/6 (67%) | 2/6 (33%) | 0 | 2 | 2 |

### Threshold

If the best BM25 score is below the threshold, the answer is "Not in this document".

- **Too high:** real questions get "Not in this document" (missed answers).
- **Too low:** trap questions get an answer from some unrelated piece (a wrong answer, worse).

Rule, fixed before looking at single questions: pick the threshold with the most correct outcomes (right page + correct other source + traps refused); on a tie pick the higher one ("never guess"). With only 29 questions and 8 traps this is a first estimate, not a final value.

| Threshold | Right | Correct, other source | Wrong | Missed | Traps refused | Traps answered | Correct total |
|---|---|---|---|---|---|---|---|
| 0.0 | 20 | 0 | 9 | 0 | 1 | 7 | 21 |
| 0.5 | 20 | 0 | 9 | 0 | 1 | 7 | 21 |
| 1.0 | 20 | 0 | 9 | 0 | 1 | 7 | 21 |
| 1.5 | 20 | 0 | 9 | 0 | 1 | 7 | 21 |
| 2.0 | 20 | 0 | 9 | 0 | 1 | 7 | 21 |
| 2.5 | 20 | 0 | 9 | 0 | 1 | 7 | 21 |
| 3.0 | 20 | 0 | 9 | 0 | 1 | 7 | 21 |
| 3.5 | 20 | 0 | 9 | 0 | 1 | 7 | 21 |
| 4.0 | 20 | 0 | 9 | 0 | 1 | 7 | 21 |
| 4.5 | 20 | 0 | 9 | 0 | 1 | 7 | 21 |
| 5.0 | 20 | 0 | 9 | 0 | 1 | 7 | 21 |
| 5.5 | 20 | 0 | 9 | 0 | 2 | 6 | 22 |
| 6.0 | 20 | 0 | 9 | 0 | 3 | 5 | 23 |
| 6.5 | 20 | 0 | 9 | 0 | 3 | 5 | 23 |
| 7.0 | 20 | 0 | 9 | 0 | 3 | 5 | 23 |
| 7.5 | 20 | 0 | 9 | 0 | 3 | 5 | 23 |
| 8.0 | 19 | 0 | 9 | 1 | 3 | 5 | 22 |
| 8.5 | 19 | 0 | 8 | 2 | 3 | 5 | 22 |
| 9.0 | 19 | 0 | 8 | 2 | 5 | 3 | 24 |
| 9.5 | 19 | 0 | 8 | 2 | 5 | 3 | 24 |
| 10.0 | 19 | 0 | 8 | 2 | 5 | 3 | 24 |
| 10.5 | 19 | 0 | 7 | 3 | 6 | 2 | 25 |
| 11.0 | 19 | 0 | 7 | 3 | 6 | 2 | 25 |
| 11.5 | 19 | 0 | 6 | 4 | 7 | 1 | 26 ← chosen |
| 12.0 | 18 | 0 | 6 | 5 | 7 | 1 | 25 |
| 12.5 | 18 | 0 | 5 | 6 | 7 | 1 | 25 |
| 13.0 | 18 | 0 | 5 | 6 | 7 | 1 | 25 |
| 13.5 | 18 | 0 | 5 | 6 | 7 | 1 | 25 |
| 14.0 | 17 | 0 | 5 | 7 | 7 | 1 | 24 |
| 14.5 | 16 | 0 | 4 | 9 | 7 | 1 | 23 |
| 15.0 | 16 | 0 | 3 | 10 | 7 | 1 | 23 |
| 15.5 | 15 | 0 | 3 | 11 | 7 | 1 | 22 |
| 16.0 | 15 | 0 | 3 | 11 | 8 | 0 | 23 |
| 16.5 | 15 | 0 | 3 | 11 | 8 | 0 | 23 |
| 17.0 | 15 | 0 | 3 | 11 | 8 | 0 | 23 |
| 17.5 | 14 | 0 | 3 | 12 | 8 | 0 | 22 |
| 18.0 | 14 | 0 | 3 | 12 | 8 | 0 | 22 |
| 18.5 | 14 | 0 | 2 | 13 | 8 | 0 | 22 |
| 19.0 | 14 | 0 | 2 | 13 | 8 | 0 | 22 |
| 19.5 | 12 | 0 | 2 | 15 | 8 | 0 | 20 |
| 20.0 | 11 | 0 | 2 | 16 | 8 | 0 | 19 |

### Correct, other source

None.

### Failed questions

- **NAV-05** (wrong) expected nav_rules.pdf p.106: How long is a prolonged blast under the Inland Rules?  
  Returned: answered; top 1: nav_rules.pdf p.110, score 14.5: "(e) A vessel nearing a bend or an area of a channel or fairway where other vessels may be obscured by an intervening obs..."; also: nav_rules.pdf p.105 (13.8), nav_rules.pdf p.110 (13.6)
- **NAV-09** (wrong) expected nav_rules.pdf p.15|16: Do both the International and Inland Rules define a vessel constrained by her draft?  
  Returned: answered; top 1: nav_rules.pdf p.37, score 18.1: "(ii) A vessel constrained by her draft shall navigate with particular caution having full regard to her special conditio..."; also: nav_rules.pdf p.95 (17.6), nav_rules.pdf p.37 (16.4)
- **NAV-10** (wrong) expected nav_rules.pdf p.45: How far away must the top white light of a big ship (50 m or longer) be visible under the International Rules?  
  Returned: answered; top 1: nav_rules.pdf p.143, score 14.4: "(m) a ship-to-shore distress alert transmitted by the ship’s Inmarsat or other mobile satellite service provider ship ea..."; also: nav_rules.pdf p.107 (13.5), nav_rules.pdf p.125 (13.2)
- **NAV-11** (wrong) expected nav_rules.pdf p.109: What horn signal do I give under the International Rules if I do not understand what the other ship is doing?  
  Returned: answered; top 1: nav_rules.pdf p.163, score 12.2: "(d) An east-west line (latitude 30°14.7’ N.) drawn between the westernmost extremity of Horn Island to the easternmost e..."; also: nav_rules.pdf p.113 (11.9), coast_pilot4_ch1.pdf p.22 (11.0)
- **BG-03** (wrong) expected boaters_guide.pdf p.16: What conditions must pyrotechnic visual distress signals meet?  
  Returned: answered; top 1: boaters_guide.pdf p.17, score 23.9: "Non-pyrotechnic visual distress signals must be in serviceable condition, readily accessible, and certified by the manuf..."; also: boaters_guide.pdf p.16 (23.4), boaters_guide.pdf p.17 (21.0)
- **BG-05** (wrong) expected boaters_guide.pdf p.16: When do pyrotechnic visual distress signals expire?  
  Returned: answered; top 1: boaters_guide.pdf p.17, score 23.9: "Non-pyrotechnic visual distress signals must be in serviceable condition, readily accessible, and certified by the manuf..."; also: boaters_guide.pdf p.16 (20.7), boaters_guide.pdf p.17 (18.7)
- **BG-07** (missed) expected boaters_guide.pdf p.16: How long are boat flares good for after they are made?  
  Returned: Not in this document; top 1: coast_pilot4_ch1.pdf p.2, score 11.1: "(21) These are true and are given in degrees clockwise from 000° (north) to 359°. The courses given are the courses to b..."; also: boaters_guide.pdf p.17 (10.2), boaters_guide.pdf p.42 (9.1)
- **CP-02** (missed) expected coast_pilot4_ch1.pdf p.2: What does squat mean?  
  Returned: Not in this document; top 1: coast_pilot4_ch1.pdf p.2, score 8.0: "(36) Squat denotes a change in trim of a ship underway, relative to her trim when stopped. It usually causes the stern o..."; also: coast_pilot4_ch1.pdf p.2 (7.7), nav_rules.pdf p.107 (7.6)
- **CP-04** (missed) expected coast_pilot4_ch1.pdf p.2: How long is a nautical mile?  
  Returned: Not in this document; top 1: coast_pilot4_ch1.pdf p.26, score 10.5: "(355) The Three Nautical Mile Line, as measured from the territorial sea baselines and previously identified as the 25 O..."; also: nav_rules.pdf p.196 (10.0), coast_pilot4_ch1.pdf p.3 (9.7)
- **CP-08** (missed) expected coast_pilot4_ch1.pdf p.2: In simple words, what is squat?  
  Returned: Not in this document; top 1: nav_rules.pdf p.17, score 8.1: "(j) The words length and breadth of a vessel mean her length overall and greatest breadth."; also: nav_rules.pdf p.18 (8.1), coast_pilot4_ch1.pdf p.2 (8.0)
- **TRAP-NAV-02** (trap_answered) expected "Not in this document": How many hours of rest must a watchkeeper have in any 24-hour period under STCW?  
  Returned: answered; top 1: coast_pilot4_ch1.pdf p.31, score 15.9: "(424) 2. Has diarrhea, defined as the occurrence in a 24 hour period of three or more loose stools or of a greater than ..."; also: coast_pilot4_ch1.pdf p.31 (13.0), coast_pilot4_ch1.pdf p.20 (9.9)

### Right page, but exact answer not in the top-1 piece

- **NAV-04** expected "6 miles"  
  Top-1 piece: "(b) In vessels of 12 meters or more in length but less than 50 meters in length: − a masthead light, 5 miles; except that where the length of the vessel is less..."
- **NAV-07** expected "International: “I am altering my course to starboard”. Inland: “I intend to leave you on my port side”."  
  Top-1 piece: "(a) When vessels are in sight of one another, a power-driven vessel underway, when maneuvering as authorized or required by these Rules, shall indicate that man..."
- **NAV-08** expected "International: an all-round white light visible at a minimum range of 5 miles. Inland: one all-round white or yellow light visible at a minimum range of 2 miles."  
  Top-1 piece: "(b) A vessel may supplement the whistle signals prescribed in paragraph (a) of this Rule by light signals:"
- **NAV-12** expected "Between 70-200 Hz."  
  Top-1 piece: "(a) Frequencies and range of audibility The fundamental frequency of the signal shall lie within the range 70-700 Hz. The range of audibility of the signal from..."
<!-- END phase3-baseline -->

<!-- BEGIN phase4-search -->
## Phase 4 search choice (no AI)

All 3 PDFs in one index (2149 pieces). The AI gets the top **5** pieces, so the main number is "right doc + page among the 5 pieces sent".
Choice rule, fixed before looking at single questions: most right in the pieces sent; tie -> more right in top 1; tie -> the simpler option. The first run ended in an exact tie on all three, so one tie-break was added before "simpler": more compare questions with both pages sent (a compare answer needs both pages).

| Search | Right page in top 5 | Right page top 1 | Compare: both pages sent | Avg search time |
|---|---|---|---|---|
| BM25 | 27/29 | 20/29 | 2/3 | 2 ms |
| BM25 + rule set | 27/29 | 20/29 | 2/3 | 3 ms |
| Embeddings all-MiniLM-L6-v2 | 26/29 | 18/29 | 2/3 | 1865 ms |
| Embeddings all-MiniLM-L6-v2 + rule set | 27/29 | 20/29 | 2/3 | 20 ms |
| Hybrid RRF (all-MiniLM-L6-v2) | 28/29 | 22/29 | 2/3 | 27 ms |
| Hybrid RRF (all-MiniLM-L6-v2) + rule set | 28/29 | 24/29 | 2/3 | 23 ms |
| Hybrid RRF (all-MiniLM-L6-v2) + rule set + re-ranker | 29/29 | 27/29 | 1/3 | 520 ms |
| Embeddings bge-small-en-v1.5 | 29/29 | 24/29 | 2/3 | 44 ms |
| Embeddings bge-small-en-v1.5 + rule set | 29/29 | 25/29 | 2/3 | 26 ms |
| Hybrid RRF (bge-small-en-v1.5) | 29/29 | 24/29 | 2/3 | 29 ms |
| Hybrid RRF (bge-small-en-v1.5) + rule set | 29/29 | 24/29 | 2/3 | 30 ms |
| Hybrid RRF (bge-small-en-v1.5) + rule set + re-ranker **← chosen** | 29/29 | 27/29 | 2/3 | 699 ms |

Rule-set check: 10 questions name one rule set; their expected page has that rule set's label in 10/10 cases (labels come from page headings).
<!-- END phase4-search -->

<!-- BEGIN phase4-answers -->
## Phase 4: hybrid search + AI answer + proof check (run 5: rule-set sources, retry every 5, warm-up)

- Search: `hybrid` (BM25 + `BAAI/bge-small-en-v1.5`, RRF), rule-set filter on, re-ranker `cross-encoder/ms-marco-MiniLM-L6-v2`; top 5 pieces sent to the AI
- AI: gemini:gemini-3.1-flash-lite, groq:openai/gpt-oss-120b (in this order), timeout 5 s (main) / 15 s (fallback), all within 9 s per question, no retries; prompt version 4
- Every answer passed the proof check (quote on its page, numbers + units in the quote, page was sent, rule set, topic, one source unless comparing, every number of the quote in the answer) or was replaced by "Not in this document"
- **Wrong** = answer shown is not supported by the expected source, OR its numbers differ from the expected answer's numbers

| Measure | Phase 3 baseline | Phase 4 | Target |
|---|---|---|---|
| Right doc + page | 18/29 (62%) | 20/29 (69%) | reported (aim 9 of 10, not a gate) |
| Exact answer (all numbers + key words) | 15/29 (52%) | 18/29 (62%) | (tracked) |
| Correct, other source | 1 | 0 | |
| Traps "Not in this document" | 7/8 (88%) | 8/8 (100%) | all |
| **Wrong** | 6 | **0** | **0** |
| **Traps answered** | 1 | **0** | **0** |
| Missed (real question, said "Not in this document") | 4 | 7 | |
| Not tested (AI busy; the run is incomplete if > 0) | n/a | 2 | 0 |
| Answer time (search + AI + check), new answers | ~2 ms (search only) | avg 4.4 s, max 7.9 s | under 10 s |

**Completed on 3 Nov 2026** (same code, same budgets): only NAV-02 and NAV-08 asked again with `--ids NAV-02,NAV-08 --fresh --pause 10 --max-calls 4`. First try: Gemini warm-up timeout, nothing asked (1 call). After 10 min: warm-up ok 2.4 s; NAV-02 **right** 7.1 s, NAV-08 **right** 7.3 s (both: Gemini timeout 5 s -> Groq ok); 5 calls. With the 35 run-5 answers: right page 22/29, wrong 0, traps 8/8, not tested 0, max time 9.0 s -> **eval set passes the Phase 4 gate**.

Which AI answered: groq:openai/gpt-oss-120b 30, gemini:gemini-3.1-flash-lite 5, none (no AI answer) 2

#### Per document

| Document | Questions | Right page | Correct, other source | Wrong | Missed |
|---|---|---|---|---|---|
| boaters_guide.pdf | 8 | 7/8 (88%) | 0 | 0 | 1 |
| coast_pilot4_ch1.pdf | 8 | 7/8 (88%) | 0 | 0 | 1 |
| nav_rules.pdf | 13 | 6/13 (46%) | 0 | 0 | 5 |

### Per question: outcome and which AI answered

| Question | Outcome | AI that answered | Time (new answers) |
|---|---|---|---|
| NAV-01 | right | gemini:gemini-3.1-flash-lite | 4.1 s |
| NAV-02 | not_tested | none (AI busy) | 9.0 s |
| NAV-03 | right | groq:openai/gpt-oss-120b | 5.6 s |
| NAV-04 | right | groq:openai/gpt-oss-120b | 4.7 s |
| NAV-05 | right | groq:openai/gpt-oss-120b | 4.6 s |
| NAV-06 | missed | groq:openai/gpt-oss-120b | 3.8 s |
| NAV-07 | missed | groq:openai/gpt-oss-120b | 3.4 s |
| NAV-08 | not_tested | none (AI busy) | 9.0 s |
| NAV-09 | missed | groq:openai/gpt-oss-120b | 4.5 s |
| NAV-10 | missed | groq:openai/gpt-oss-120b | 3.3 s |
| NAV-11 | missed | groq:openai/gpt-oss-120b | 4.2 s |
| NAV-12 | right | groq:openai/gpt-oss-120b | 5.6 s |
| NAV-13 | right | groq:openai/gpt-oss-120b | 7.6 s |
| BG-01 | right | groq:openai/gpt-oss-120b | 2.8 s |
| BG-02 | right | groq:openai/gpt-oss-120b | 5.0 s |
| BG-03 | right | groq:openai/gpt-oss-120b | 3.1 s |
| BG-04 | right | groq:openai/gpt-oss-120b | 3.9 s |
| BG-05 | right | groq:openai/gpt-oss-120b | 7.9 s |
| BG-06 | right | groq:openai/gpt-oss-120b | 2.6 s |
| BG-07 | right | groq:openai/gpt-oss-120b | 2.9 s |
| BG-08 | missed | groq:openai/gpt-oss-120b | 4.1 s |
| CP-01 | right | groq:openai/gpt-oss-120b | 2.5 s |
| CP-02 | right | groq:openai/gpt-oss-120b | 5.2 s |
| CP-03 | right | groq:openai/gpt-oss-120b | 3.7 s |
| CP-04 | right | groq:openai/gpt-oss-120b | 5.9 s |
| CP-05 | right | groq:openai/gpt-oss-120b | 3.7 s |
| CP-06 | right | groq:openai/gpt-oss-120b | 5.4 s |
| CP-07 | missed | groq:openai/gpt-oss-120b | 6.0 s |
| CP-08 | right | groq:openai/gpt-oss-120b | 2.9 s |
| TRAP-NAV-01 | refused | groq:openai/gpt-oss-120b | 7.5 s |
| TRAP-NAV-02 | refused | groq:openai/gpt-oss-120b | 1.8 s |
| TRAP-NAV-03 | refused | groq:openai/gpt-oss-120b | 2.0 s |
| TRAP-BG-01 | refused | gemini:gemini-3.1-flash-lite | 4.0 s |
| TRAP-BG-02 | refused | groq:openai/gpt-oss-120b | 7.7 s |
| TRAP-BG-03 | refused | gemini:gemini-3.1-flash-lite | 6.4 s |
| TRAP-CP-01 | refused | gemini:gemini-3.1-flash-lite | 3.1 s |
| TRAP-CP-02 | refused | gemini:gemini-3.1-flash-lite | 2.5 s |

### Failed questions

- **NAV-02** (not_tested) expected nav_rules.pdf p.17: What does the word underway mean under the International Rules?  
  Reason: ai_busy (gemini:gemini-3.1-flash-lite timeout 5.0 s -> groq:openai/gpt-oss-120b timeout 3.3 s)  
  Shown: The AI is busy right now. Here are the best matching pieces from your document instead.
- **NAV-06** (missed) expected nav_rules.pdf p.111: Under the International Rules, in restricted visibility, what does a power-driven vessel underway but stopped and making no way through the water sound, and how often?  
  Reason: proof:quote_not_focused (quote has other measurements: 2 second)  
  Shown: Not in this document  
  AI calls: gemini:gemini-3.1-flash-lite switched_off 0.0 s -> groq:openai/gpt-oss-120b ok 2.1 s
- **NAV-07** (missed) expected nav_rules.pdf p.107|108: When power-driven vessels in sight of one another manoeuvre, what does one short blast mean under the International Rules and under the Inland Rules?  
  Reason: llm_not_found  
  Shown: Not in this document  
  AI calls: gemini:gemini-3.1-flash-lite switched_off 0.0 s -> groq:openai/gpt-oss-120b ok 1.7 s
- **NAV-08** (not_tested) expected nav_rules.pdf p.107|108: What light may supplement manoeuvring whistle signals and what is its minimum range under the International and Inland Rules?  
  Reason: ai_busy (gemini:gemini-3.1-flash-lite unavailable 4.8 s -> groq:openai/gpt-oss-120b timeout 2.0 s)  
  Shown: The AI is busy right now. Here are the best matching pieces from your document instead.
- **NAV-09** (missed) expected nav_rules.pdf p.15|16: Do both the International and Inland Rules define a vessel constrained by her draft?  
  Reason: llm_not_found  
  Shown: Not in this document  
  AI calls: gemini:gemini-3.1-flash-lite switched_off 0.0 s -> groq:openai/gpt-oss-120b ok 0.9 s
- **NAV-10** (missed) expected nav_rules.pdf p.45: How far away must the top white light of a big ship (50 m or longer) be visible under the International Rules?  
  Reason: proof:off_topic (question numbers not in the quote: 50)  
  Shown: Not in this document  
  AI calls: gemini:gemini-3.1-flash-lite switched_off 0.0 s -> groq:openai/gpt-oss-120b ok 0.9 s
- **NAV-11** (missed) expected nav_rules.pdf p.109: What horn signal do I give under the International Rules if I do not understand what the other ship is doing?  
  Reason: proof:off_topic (quote has none of the question's words: the vessel in doubt shall immediately indicate such doubt by)  
  Shown: Not in this document  
  AI calls: gemini:gemini-3.1-flash-lite switched_off 0.0 s -> groq:openai/gpt-oss-120b ok 2.2 s
- **BG-08** (missed) expected boaters_guide.pdf p.9: How tall do the numbers on the side of my boat have to be?  
  Reason: proof:off_topic (quote has none of the question's words: Lettering must be in plain, vertical block characters of not)  
  Shown: Not in this document  
  AI calls: gemini:gemini-3.1-flash-lite switched_off 0.0 s -> groq:openai/gpt-oss-120b ok 1.9 s
- **CP-07** (missed) expected coast_pilot4_ch1.pdf p.2: Roughly how many yards are in one nautical mile?  
  Reason: proof:quote_not_focused (quote has other measurements: 1.15 statute mile)  
  Shown: Not in this document  
  AI calls: gemini:gemini-3.1-flash-lite unavailable 1.4 s -> groq:openai/gpt-oss-120b ok 1.5 s

### All answers shown

- **NAV-01** (right): A vessel restricted in her ability to maneuver is a vessel which from the nature of her work is restricted in her ability to maneuver as required by t...  
  Source: nav_rules.pdf p.15 (—INTERNATIONAL— General Rule 3 General Definitions); quote: "(g) The term vessel restricted in her ability to maneuver means a vessel which from the nature of her work is restricted in her ability to maneuver as required ..."
- **NAV-03** (right): at least five short and rapid blasts on the whistle, may be supplemented by at least five short and rapid flashes  
  Source: nav_rules.pdf p.109 (—INTERNATIONAL— Sound and Light Signals Rule 34—CONTINUED); quote: "the vessel in doubt shall immediately indicate such doubt by giving at least five short and rapid blasts on the whistle. Such signal may be supplemented by a li..."
- **NAV-04** (right): 6 miles  
  Source: nav_rules.pdf p.45 (—INTERNATIONAL— Lights and Shapes Rule 22 Visibility of Ligh...); quote: "In vessels of 50 meters or more in length: − a masthead light, 6 miles;"
- **NAV-05** (right): from 4 to 6 seconds’ duration  
  Source: nav_rules.pdf p.106 (SUBPART D—SOUND AND LIGHT SIGNALS Rule 32 Definitions); quote: "The term prolonged blast means a blast of from 4 to 6 seconds’ duration."
- **NAV-12** (right): 70-200 Hz  
  Source: nav_rules.pdf p.137 (—INTERNATIONAL— Annex III Technical Details of Sound Signal ...); quote: "70-200 Hz, for a vessel 200 meters or more in length;"
- **NAV-13** (right): A high intensity white light flashing at regular intervals from 50 to 70 times per minute.  
  Source: nav_rules.pdf p.116 (—INLAND— Sound and Light Signals Rule 37 Distress Signals); quote: "A high intensity white light flashing at regular intervals from 50 to 70 times per minute."
- **BG-01** (right): anchors, paddles, rearview mirrors, or diver/ski flags  
  Source: boaters_guide.pdf p.12 (Equipment Requirements); quote: "The Coast Guard does not regulate anchors, paddles, rearview mirrors, or diver/ski flags."
- **BG-02** (right): Mark the name and hailing port of the vessel together in one place on the hull (usually on the stern).  
  Source: boaters_guide.pdf p.10 (); quote: "Mark the name and hailing port of the vessel together in one place on the hull (usually on the stern)."
- **BG-03** (right): Pyrotechnic visual distress signals must be U.S. Coast Guard-approved, not expired, in serviceable condition, and readily accessible.  
  Source: boaters_guide.pdf p.16 (Pyrotechnic Devices); quote: "Pyrotechnic visual distress signals must be U.S. Coast Guard-approved, not expired, in serviceable condition, and readily accessible."
- **BG-04** (right): not less than 3 inches in height  
  Source: boaters_guide.pdf p.9 (Display of Numbers); quote: "Lettering must be in plain, vertical block characters of not less than 3 inches in height."
- **BG-05** (right): 42 months after the date of manufacture  
  Source: boaters_guide.pdf p.16 (Pyrotechnic Devices); quote: "Check the expiration date (42 months after the date of manufacture)."
- **BG-06** (right): at least 5 by 8 inches  
  Source: boaters_guide.pdf p.26 (Pollution Regulations (33 CFR 151/155)); quote: "Vessels 26 feet and greater in length, with machinery spaces, must display a placard at least 5 by 8 inches, made of durable material, fixed in a conspicuous pl..."
- **BG-07** (right): 42 months after the date of manufacture  
  Source: boaters_guide.pdf p.16 (Pyrotechnic Devices); quote: "Check the expiration date (42 months after the date of manufacture)."
- **CP-01** (right): The controlling depth is the least known depth of a channel as determined by hydrographic surveys and restricts the safe use of the channel to drafts ...  
  Source: coast_pilot4_ch1.pdf p.2 (Depths); quote: "(26) The controlling depth is the least known depth of a channel as determined by hydrographic surveys and restricts the safe use of the channel to drafts less ..."
- **CP-02** (right): Squat denotes a change in trim of a ship underway, relative to her trim when stopped.  
  Source: coast_pilot4_ch1.pdf p.2 (Under-keel clearances); quote: "Squat denotes a change in trim of a ship underway, relative to her trim when stopped."
- **CP-03** (right): above mean high water  
  Source: coast_pilot4_ch1.pdf p.1 (Bridges and Cables); quote: "Vertical clearances of bridges and overhead cables are in feet above mean high water unless otherwise stated; clearances in Coast Pilot 6 are in feet above Low ..."
- **CP-04** (right): 1,852 meters / 6,076.12 feet  
  Source: coast_pilot4_ch1.pdf p.34 (Measurements and Equivalencies); quote: "nautical mile — 1,852 meters / 6,076.12 feet"
- **CP-05** (right): when the depth is less than seven times the draft of the ship  
  Source: coast_pilot4_ch1.pdf p.2 (Under-keel clearances); quote: "Settlement is appreciable when the depth is less than seven times the draft of the ship and increases as the depth decreases and the speed increases."
- **CP-06** (right): All ships of length 20m or greater  
  Source: coast_pilot4_ch1.pdf p.15 (U.S. VHF Channel Information Ship Frequency (MHz) New Old Ch...); quote: "All ships of length 20m or greater are required to guard VHF channel 13, in addition to VHF channel 16, when operating within U.S. territorial waters."
- **CP-08** (right): Squat denotes a change in trim of a ship underway, relative to her trim when stopped.  
  Source: coast_pilot4_ch1.pdf p.2 (Under-keel clearances); quote: "(36) Squat denotes a change in trim of a ship underway, relative to her trim when stopped."
<!-- END phase4-answers -->

<!-- BEGIN phase4-topic-threshold -->
## Phase 4: topic threshold for paraphrased questions

Re-ranker `cross-encoder/ms-marco-MiniLM-L6-v2` score of (question, quote). Used only when the quote shares no word with the question. Chosen by `scripts/choose_topic_threshold.py` (no AI calls).

- Highest bad-quote score (trap quotes + wrong-number quotes): **8.07** (CP-07)
- Lowest safe threshold: **8.07**
- Right quotes at or above it: 6/32; of the right quotes that share no word with their question: 0/3

Decision: **no safe threshold**. Every right quote that shares no word with its question scores below the bad quotes, so any threshold that lets it pass would also let bad quotes pass. `TOPIC_MIN_SCORE` stays `None` (off): such answers stay "Not in this document".

| Right quote (question) | Score | Shares a word | Passes threshold |
|---|---|---|---|
| NAV-01 | 5.02 | yes | no |
| NAV-02 | 6.04 | yes | no |
| NAV-03 | 1.73 | yes | no |
| NAV-04 | 3.99 | yes | no |
| NAV-05 | 4.68 | yes | no |
| NAV-06 | 6.06 | yes | no |
| NAV-07 | -1.94 | yes | no |
| NAV-07 | -1.55 | yes | no |
| NAV-08 | -0.76 | yes | no |
| NAV-08 | -0.63 | yes | no |
| NAV-09 | 4.20 | yes | no |
| NAV-09 | -10.72 | no | no |
| NAV-10 | -1.87 | yes | no |
| NAV-11 | -8.79 | no | no |
| NAV-12 | 4.06 | yes | no |
| NAV-13 | -3.28 | yes | no |
| BG-01 | 8.70 | yes | yes |
| BG-02 | -0.93 | yes | no |
| BG-03 | 5.87 | yes | no |
| BG-04 | -5.01 | yes | no |
| BG-05 | -4.31 | yes | no |
| BG-06 | 8.11 | yes | yes |
| BG-07 | -2.79 | yes | no |
| BG-08 | -7.82 | no | no |
| CP-01 | 9.70 | yes | yes |
| CP-02 | 7.90 | yes | no |
| CP-03 | 6.81 | yes | no |
| CP-04 | 8.99 | yes | yes |
| CP-05 | 8.48 | yes | yes |
| CP-06 | 9.85 | yes | yes |
| CP-07 | 8.07 | yes | no |
| CP-08 | 4.95 | yes | no |

| Highest bad quote per question | Score | Quote |
|---|---|---|
| CP-07 | 8.07 | A nautical mile is one minute of latitude, or approximately 2,000 yards, and is  |
| NAV-12 | 6.98 | The range of audibility of the signal from a whistle shall be determined by thos |
| CP-04 | 6.58 | A statute mile is 5,280 feet or about 0.87 nautical mile. |
| NAV-07 | 5.80 | (313) Navigation Rules, International-Inland, Rule 34(d), states that when vesse |
| NAV-04 | 5.75 | (c) The masthead light of a power-driven vessel of 12 meters but less than 20 me |
| BG-02 | 4.84 | Recreational vessels are eligible to be documented if they are wholly owned by a |
| NAV-09 | 4.58 | A vessel constrained by her draft may, in addition to the lights prescribed for  |
| CP-03 | 3.71 | See charts for the horizontal clearance of bridges, as these are generally given |
| NAV-06 | 3.71 | (a) A power-driven vessel making way through the water shall sound at intervals  |
| NAV-05 | 2.43 | (a) A power-driven vessel making way through the water shall sound at intervals  |
| NAV-10 | 2.05 | (iii) the light used for this signal shall, if fitted, be an all-round white lig |
| BG-06 | 2.01 | includes synthetic ropes, Prohibited in all areas fishing nets, and plastic bags |
<!-- END phase4-topic-threshold -->

<!-- BEGIN phase4-topic-threshold-baai-bge-reranker-base -->
## Phase 4: topic threshold for paraphrased questions (BAAI/bge-reranker-base)

Re-ranker `BAAI/bge-reranker-base` score of (question, quote). Used only when the quote shares no word with the question. Chosen by `scripts/choose_topic_threshold.py` (no AI calls).

- Highest bad-quote score (trap quotes + wrong-number quotes): **1.00** (CP-04); highest trap quote: 0.97
- Lowest safe threshold: **1.00**
- Time to score one (question, quote): avg 55 ms, max 116 ms (model load once: 48.7 s)
- Right quotes at or above it: 0/32; of the right quotes that share no word with their question: 0/3

Decision: **no safe threshold**. Every right quote that shares no word with its question scores below the bad quotes, so any threshold that lets it pass would also let bad quotes pass. `TOPIC_MIN_SCORE` stays `None` (off): such answers stay "Not in this document".

| Right quote (question) | Score | Shares a word | Passes threshold |
|---|---|---|---|
| NAV-01 | 0.94 | yes | no |
| NAV-02 | 0.99 | yes | no |
| NAV-03 | 0.53 | yes | no |
| NAV-04 | 0.99 | yes | no |
| NAV-05 | 0.95 | yes | no |
| NAV-06 | 1.00 | yes | no |
| NAV-07 | 0.97 | yes | no |
| NAV-07 | 0.98 | yes | no |
| NAV-08 | 0.23 | yes | no |
| NAV-08 | 0.39 | yes | no |
| NAV-09 | 1.00 | yes | no |
| NAV-09 | 0.00 | no | no |
| NAV-10 | 0.93 | yes | no |
| NAV-11 | 0.00 | no | no |
| NAV-12 | 1.00 | yes | no |
| NAV-13 | 0.07 | yes | no |
| BG-01 | 0.99 | yes | no |
| BG-02 | 0.66 | yes | no |
| BG-03 | 0.82 | yes | no |
| BG-04 | 0.99 | yes | no |
| BG-05 | 0.34 | yes | no |
| BG-06 | 1.00 | yes | no |
| BG-07 | 0.49 | yes | no |
| BG-08 | 0.10 | no | no |
| CP-01 | 1.00 | yes | no |
| CP-02 | 0.95 | yes | no |
| CP-03 | 1.00 | yes | no |
| CP-04 | 1.00 | yes | no |
| CP-05 | 0.13 | yes | no |
| CP-06 | 0.92 | yes | no |
| CP-07 | 1.00 | yes | no |
| CP-08 | 0.91 | yes | no |

| Highest bad quote per question | Score | Quote |
|---|---|---|
| CP-04 | 1.00 | nautical mile — 1,852 meters / 6,076.12 feet 25 OCT 2026 acre — 43,560 square fe |
| CP-07 | 1.00 | A nautical mile is one minute of latitude, or approximately 2,000 yards, and is  |
| BG-04 | 0.99 | Use letters not less than 4 inches in height. |
| NAV-07 | 0.98 | (313) Navigation Rules, International-Inland, Rule 34(d), states that when vesse |
| TRAP-BG-01 | 0.97 | In addition to the requirements stated in this document, the owner/operator may  |
| NAV-09 | 0.97 | A vessel constrained by her draft may, in addition to the lights prescribed for  |
| BG-08 | 0.96 | In consideration of procedures and for potential conflict between aircraft and m |
| NAV-12 | 0.95 | The range of audibility of the signal from a whistle shall be determined by thos |
| NAV-10 | 0.94 | (iii) the light used for this signal shall, if fitted, be an all-round white lig |
| BG-06 | 0.94 | includes synthetic ropes, Prohibited in all areas fishing nets, and plastic bags |
| BG-01 | 0.87 | Coast Guard conducts nearly 55,000 boardings a year in its multiple roles: enfor |
| NAV-06 | 0.82 | (a) A power-driven vessel making way through the water shall sound at intervals  |
<!-- END phase4-topic-threshold-baai-bge-reranker-base -->

<!-- BEGIN phase4-holdout -->
## Phase 4: hold-out set (10 questions + 2 traps, run once)

- Search: `hybrid` (BM25 + `BAAI/bge-small-en-v1.5`, RRF), rule-set filter on, re-ranker `cross-encoder/ms-marco-MiniLM-L6-v2`; top 5 pieces sent to the AI
- AI: gemini:gemini-3.1-flash-lite, groq:openai/gpt-oss-120b (in this order), timeout 5 s (main) / 15 s (fallback), all within 9 s per question, no retries; prompt version 4
- Every answer passed the proof check (quote on its page, numbers + units in the quote, page was sent, rule set, topic, one source unless comparing, every number of the quote in the answer) or was replaced by "Not in this document"
- **Wrong** = answer shown is not supported by the expected source, OR its numbers differ from the expected answer's numbers

| Measure | Phase 3 baseline | Phase 4 | Target |
|---|---|---|---|
| Right doc + page | 8/10 (80%) | 6/10 (60%) | reported (aim 9 of 10, not a gate) |
| Exact answer (all numbers + key words) | 8/10 (80%) | 7/10 (70%) | (tracked) |
| Correct, other source | 0 | 0 | |
| Traps "Not in this document" | 1/2 (50%) | 2/2 (100%) | all |
| **Wrong** | 1 | **1** | **0** |
| **Traps answered** | 1 | **0** | **0** |
| Missed (real question, said "Not in this document") | 1 | 3 | |
| Not tested (AI busy; the run is incomplete if > 0) | n/a | 0 | 0 |
| Answer time (search + AI + check), new answers | ~2 ms (search only) | avg 1.8 s, max 3.0 s | under 10 s |

**Re-scored on 3 Nov 2026: p.28 added after the run; original score was wrong 1.** HO-CP-01 showed "every 4 to 6 minutes" from coast_pilot4_ch1.pdf p.28 ("These broadcasts repeat recorded messages every 4 to 6 minutes.", NOAA Weather Radio, paragraph 393), the same fact as the row's p.17 in other words. With Hari's OK, p.28 was added to the row's `other_answers` (checker-verified on the page; the new same-fact check lists it) and the saved answers were scored again (0 AI calls, same answers): right page **7/10**, **wrong 0**, traps 2/2, missed 3; answer times unchanged (from the live run above, max 3.0 s) -> hold-out passes the Phase 4 gate. The table above is the original live-run score.

Which AI answered: groq:openai/gpt-oss-120b 12

#### Per document

| Document | Questions | Right page | Correct, other source | Wrong | Missed |
|---|---|---|---|---|---|
| boaters_guide.pdf | 3 | 2/3 (67%) | 0 | 0 | 1 |
| coast_pilot4_ch1.pdf | 3 | 2/3 (67%) | 0 | 1 | 0 |
| nav_rules.pdf | 4 | 2/4 (50%) | 0 | 0 | 2 |

### Per question: outcome and which AI answered

| Question | Outcome | AI that answered | Time (new answers) |
|---|---|---|---|
| HO-NAV-01 | right | groq:openai/gpt-oss-120b | 2.2 s |
| HO-NAV-02 | missed | groq:openai/gpt-oss-120b | 1.6 s |
| HO-NAV-03 | right | groq:openai/gpt-oss-120b | 1.8 s |
| HO-NAV-04 | missed | groq:openai/gpt-oss-120b | 1.8 s |
| HO-BG-01 | right | groq:openai/gpt-oss-120b | 2.4 s |
| HO-BG-02 | right | groq:openai/gpt-oss-120b | 2.1 s |
| HO-BG-03 | missed | groq:openai/gpt-oss-120b | 1.9 s |
| HO-CP-01 | wrong | groq:openai/gpt-oss-120b | 1.6 s |
| HO-CP-02 | right | groq:openai/gpt-oss-120b | 1.5 s |
| HO-CP-03 | right | groq:openai/gpt-oss-120b | 3.0 s |
| TRAP-HO-NAV-01 | refused | groq:openai/gpt-oss-120b | 1.3 s |
| TRAP-HO-BG-01 | refused | groq:openai/gpt-oss-120b | 1.1 s |

### Failed questions

- **HO-NAV-02** (missed) expected nav_rules.pdf p.112: Under the Inland Rules, what sound signal must a manned vessel being towed give in restricted visibility?  
  Reason: proof:quote_not_focused (quote has other measurements: 2 minute)  
  Shown: Not in this document  
  AI calls: gemini:gemini-3.1-flash-lite switched_off 0.0 s -> groq:openai/gpt-oss-120b ok 1.3 s
- **HO-NAV-04** (missed) expected nav_rules.pdf p.111: Under the International Rules, in fog, what horn signal does my motor ship give when it is stopped and not moving through the water?  
  Reason: proof:quote_not_focused (quote has other measurements: 2 minute)  
  Shown: Not in this document  
  AI calls: gemini:gemini-3.1-flash-lite switched_off 0.0 s -> groq:openai/gpt-oss-120b ok 1.3 s
- **HO-BG-03** (missed) expected boaters_guide.pdf p.35: If I am caught driving my boat drunk, how big can the federal civil fine be?  
  Reason: proof:quote_not_focused (quote has other measurements: 5000 usd)  
  Shown: Not in this document  
  AI calls: gemini:gemini-3.1-flash-lite switched_off 0.0 s -> groq:openai/gpt-oss-120b ok 1.3 s
- **HO-CP-01** (wrong) expected coast_pilot4_ch1.pdf p.17: How often are NOAA Weather Radio messages repeated?  
  Reason: answer shown is not supported by the expected source  
  Shown: "every 4 to 6 minutes" from coast_pilot4_ch1.pdf p.28 (Marine Weather Forecasts)  
  AI calls: gemini:gemini-3.1-flash-lite switched_off 0.0 s -> groq:openai/gpt-oss-120b ok 0.9 s

### All answers shown

- **HO-NAV-01** (right): at intervals of not more than 2 minutes  
  Source: nav_rules.pdf p.111 (—INTERNATIONAL— Sound and Light Signals Rule 35 Sound Signal...); quote: "A power-driven vessel making way through the water shall sound at intervals of not more than 2 minutes one prolonged blast."
- **HO-NAV-03** (right): at intervals of not more than 1 minute, ring the bell rapidly for about 5 seconds  
  Source: nav_rules.pdf p.114 (—INLAND— Sound and Light Signals Rule 35—CONTINUED); quote: "A vessel at anchor shall at intervals of not more than 1 minute ring the bell rapidly for about 5 seconds."
- **HO-BG-01** (right): $2,000 or more  
  Source: boaters_guide.pdf p.11 (Report of casualty or accident (33 CFR 173.55)); quote: "Damage to the boat and other property damage of $2,000 or more."
- **HO-BG-02** (right): children under 13 years of age must wear an appropriate U.S. Coast Guard-approved life jacket unless they are below deck or within an enclosed cabin.  
  Source: boaters_guide.pdf p.14 (Child Life Jacket Requirements); quote: "On a vessel that is underway, children under 13 years of age must wear an appropriate U.S. Coast Guard-approved life jacket unless they are: • Below deck, or • ..."
- **HO-CP-01** (wrong): every 4 to 6 minutes  
  Source: coast_pilot4_ch1.pdf p.28 (Marine Weather Forecasts); quote: "These broadcasts repeat recorded messages every 4 to 6 minutes."
- **HO-CP-02** (right): 34 to 47 knots  
  Source: coast_pilot4_ch1.pdf p.29 (NATIONAL WEATHER SERVICE COASTAL WARNING DISPLAYS DAYTIME SI...); quote: "GALE WARNING: To indicate winds within the range 34 to 47 knots are"
- **HO-CP-03** (right): in excess of 12 knots  
  Source: coast_pilot4_ch1.pdf p.22 (Small craft); quote: "Large vessels may appear to move slowly due to their large size but actually transit at speeds in excess of 12 knots, requiring a great distance in which to man..."
<!-- END phase4-holdout -->

<!-- BEGIN phase4-newpdf -->
## Phase 4: new PDF (osha3124.pdf, 5 questions + 2 traps, run once)

- Search: `hybrid` (BM25 + `BAAI/bge-small-en-v1.5`, RRF), rule-set filter on, re-ranker `cross-encoder/ms-marco-MiniLM-L6-v2`; top 5 pieces sent to the AI
- AI: gemini:gemini-3.1-flash-lite, groq:openai/gpt-oss-120b (in this order), timeout 5 s (main) / 15 s (fallback), all within 9 s per question, no retries; prompt version 4
- Every answer passed the proof check (quote on its page, numbers + units in the quote, page was sent, rule set, topic, one source unless comparing, every number of the quote in the answer) or was replaced by "Not in this document"
- **Wrong** = answer shown is not supported by the expected source, OR its numbers differ from the expected answer's numbers

| Measure | Phase 3 baseline | Phase 4 | Target |
|---|---|---|---|
| Right doc + page | 3/5 (60%) | 3/5 (60%) | reported (aim 9 of 10, not a gate) |
| Exact answer (all numbers + key words) | 2/5 (40%) | 3/5 (60%) | (tracked) |
| Correct, other source | 0 | 0 | |
| Traps "Not in this document" | 2/2 (100%) | 1/2 (50%) | all |
| **Wrong** | 1 | **0** | **0** |
| **Traps answered** | 0 | **0** | **0** |
| Missed (real question, said "Not in this document") | 1 | 2 | |
| Not tested (AI busy; the run is incomplete if > 0) | n/a | 1 | 0 |
| Answer time (search + AI + check), new answers | ~2 ms (search only) | avg 4.0 s, max 6.0 s | under 10 s |

**Completed on 4 Nov 2026** (same code, same budgets): only TRAP-OSHA-01 asked again with `--ids TRAP-OSHA-01 --fresh --pause 10 --max-calls 3`. Warm-up: Gemini timeout; Groq answered; **refused**, 4.0 s; 2 AI calls. With the 6 answers of the first run: right page 3/5, wrong 0, traps 2/2, not tested 0, slowest 8.1 s (the "AI busy" attempt; slowest answer shown 6.0 s) -> **new PDF meets the Phase 4 gate**. The table above is the first run.

Which AI answered: groq:openai/gpt-oss-120b 4, gemini:gemini-3.1-flash-lite 2, none (no AI answer) 1

#### Per document

| Document | Questions | Right page | Correct, other source | Wrong | Missed |
|---|---|---|---|---|---|
| osha3124.pdf | 5 | 3/5 (60%) | 0 | 0 | 2 |

### Per question: outcome and which AI answered

| Question | Outcome | AI that answered | Time (new answers) |
|---|---|---|---|
| OSHA-01 | right | groq:openai/gpt-oss-120b | 6.0 s |
| OSHA-02 | right | groq:openai/gpt-oss-120b | 4.1 s |
| OSHA-03 | right | groq:openai/gpt-oss-120b | 4.3 s |
| OSHA-04 | missed | groq:openai/gpt-oss-120b | 4.4 s |
| OSHA-05 | missed | gemini:gemini-3.1-flash-lite | 2.6 s |
| TRAP-OSHA-01 | not_tested | none (AI busy) | 8.1 s |
| TRAP-OSHA-02 | refused | gemini:gemini-3.1-flash-lite | 2.7 s |

### Failed questions

- **OSHA-04** (missed) expected osha3124.pdf p.8: On stairways that will not be a permanent part of the building, how big must the landings be and how often are they needed?  
  Reason: proof:quote_not_focused (quote has other measurements: 3.7 meter, 56 centimeter)  
  Shown: Not in this document  
  AI calls: gemini:gemini-3.1-flash-lite switched_off 0.0 s -> groq:openai/gpt-oss-120b ok 1.9 s
- **OSHA-05** (missed) expected osha3124.pdf p.9: What weight must handrails and top rails of stair rail systems be able to withstand?  
  Reason: proof:quote_not_focused (quote has other measurements: 2 inch, 5 centimeter)  
  Shown: Not in this document  
  AI calls: gemini:gemini-3.1-flash-lite ok 1.7 s
- **TRAP-OSHA-01** (not_tested) expected "Not in this document": What is the maximum working height of a scissor lift under OSHA rules?  
  Reason: ai_busy (gemini:gemini-3.1-flash-lite timeout 5.0 s -> groq:openai/gpt-oss-120b no_time_left 0.0 s)  
  Shown: The AI is busy right now. Here are the best matching pieces from your document instead.

### All answers shown

- **OSHA-01** (right): 11.5 inches (29 cm)  
  Source: osha3124.pdf p.5 (Portable Ladders); quote: "The minimum clear distance between side rails for all portable ladders must be 11.5 inches (29 cm)."
- **OSHA-02** (right): at least 3 feet (.9 m)  
  Source: osha3124.pdf p.5 (Stepladders); quote: "When portable ladders are used for access to an upper landing surface, the side rails must extend at least 3 feet (.9 m) above the upper landing surface."
- **OSHA-03** (right): at least 30 degrees —and no more than 50 degrees  
  Source: osha3124.pdf p.8 (Defective Ladders); quote: "Stairways must be installed at least 30 degrees —and no more than 50 degrees—from the horizontal."
<!-- END phase4-newpdf -->

<!-- BEGIN phase4-closed -->
## Phase 4 closed (Hari's decision, 4 Nov 2026)

Closed on the gate: wrong 0, all traps refused, under 10 s, on all three sets. Right page is reported, not a gate.

| Set | Wrong | Traps refused | Not tested | Slowest | Right page | Missed |
|---|---|---|---|---|---|---|
| Eval (29 + 8 traps) | 0 | 8/8 | 0 | 9.0 s | 22/29 | 7 |
| Hold-out (10 + 2 traps) | 0 (original score: wrong 1) | 2/2 | 0 | 3.0 s | 7/10 | 3 |
| New PDF `osha3124.pdf` (5 + 2 traps) | 0 | 2/2 | 0 | 8.1 s | 3/5 | 2 |

Caveats:

- **Questions asked again:** the sections above show the first runs. Eval: NAV-02 and NAV-08 got "AI busy" and were asked again (same code). New PDF: TRAP-OSHA-01 got "AI busy" and was asked again (same code).
- **Hold-out row changed after the run:** p.28 added after the run; original score was wrong 1 (HO-CP-01: exact answer shown from p.28, row listed only p.17).
- **4th PDF not re-run:** eval and hold-out ran with 3 PDFs in `data/raw`. `osha3124.pdf` now shares the search, and those two sets have not been re-run with it.
- **"AI busy" can still happen:** Gemini often timed out or gave 503 on 3-4 Nov, and a fallback can run out of the 9 s budget. Never a wrong answer, but the user gets no answer. It happened again in the live timing test (OSHA-01, 9.0 s).
- **Re-ranker can be slow:** 1.0-3.9 s per question on battery with 2-3 GB RAM free, against about 0.5 s average on 3 Nov; models took 104.7 s to load (44.7 s on 3 Nov). Cause not proven: the plugged-in repeat test was not run and the power state on 3 Nov was not recorded. No fix made.
<!-- END phase4-closed -->
