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
## Phase 4: hybrid search + AI answer + proof check

- Search: `hybrid` (BM25 + `BAAI/bge-small-en-v1.5`, RRF), rule-set filter on, re-ranker `cross-encoder/ms-marco-MiniLM-L6-v2`; top 5 pieces sent to the AI
- AI: gemini:gemini-3.1-flash-lite, groq:openai/gpt-oss-120b (in this order), timeout 7 s (main) / 15 s (fallback), no retries; prompt version 2
- Every answer passed the proof check (quote on its page, numbers + units in the quote, page was sent, rule set, topic) or was replaced by "Not in this document"
- **Wrong** = answer shown is not supported by the expected source, OR its numbers differ from the expected answer's numbers

| Measure | Phase 3 baseline | Phase 4 | Target |
|---|---|---|---|
| Right doc + page | 19/29 (66%) | 18/29 (62%) | 9 of 10 or better |
| Exact answer (all numbers + key words) | 15/29 (52%) | 20/29 (69%) | (tracked) |
| Correct, other source | 0 | 0 | |
| Traps "Not in this document" | 7/8 (88%) | 8/8 (100%) | all |
| **Wrong** | 6 | **3** | **0** |
| **Traps answered** | 1 | **0** | **0** |
| Missed (real question, said "Not in this document") | 4 | 6 | |
| Not tested (AI busy; the run is incomplete if > 0) | n/a | 2 | 0 |
| Answer time (search + AI + check), new answers | ~2 ms (search only) | avg 2.1 s, max 3.1 s | under 10 s |

Which AI answered: groq:openai/gpt-oss-120b 35, none (no AI answer) 2

#### Per document

| Document | Questions | Right page | Correct, other source | Wrong | Missed |
|---|---|---|---|---|---|
| boaters_guide.pdf | 8 | 5/8 (62%) | 0 | 1 | 2 |
| coast_pilot4_ch1.pdf | 8 | 6/8 (75%) | 0 | 0 | 0 |
| nav_rules.pdf | 13 | 7/13 (54%) | 0 | 2 | 4 |

### Per question: outcome and which AI answered

| Question | Outcome | AI that answered | Time (new answers) |
|---|---|---|---|
| NAV-01 | right | groq:openai/gpt-oss-120b | 3.0 s |
| NAV-02 | right | groq:openai/gpt-oss-120b | 1.9 s |
| NAV-03 | right | groq:openai/gpt-oss-120b | 2.0 s |
| NAV-04 | right | groq:openai/gpt-oss-120b | 1.9 s |
| NAV-05 | missed | groq:openai/gpt-oss-120b | 1.9 s |
| NAV-06 | right | groq:openai/gpt-oss-120b | 2.4 s |
| NAV-07 | missed | groq:openai/gpt-oss-120b | 2.4 s |
| NAV-08 | wrong | groq:openai/gpt-oss-120b | 2.9 s |
| NAV-09 | missed | groq:openai/gpt-oss-120b | 2.1 s |
| NAV-10 | wrong | groq:openai/gpt-oss-120b | 2.2 s |
| NAV-11 | missed | groq:openai/gpt-oss-120b | 2.0 s |
| NAV-12 | right | groq:openai/gpt-oss-120b | 3.1 s |
| NAV-13 | right | groq:openai/gpt-oss-120b | 2.7 s |
| BG-01 | right | groq:openai/gpt-oss-120b | 1.9 s |
| BG-02 | right | groq:openai/gpt-oss-120b | 2.0 s |
| BG-03 | wrong | groq:openai/gpt-oss-120b | 2.0 s |
| BG-04 | right | groq:openai/gpt-oss-120b | 2.1 s |
| BG-05 | right | groq:openai/gpt-oss-120b | 1.9 s |
| BG-06 | missed | groq:openai/gpt-oss-120b | 2.3 s |
| BG-07 | right | groq:openai/gpt-oss-120b | 1.9 s |
| BG-08 | missed | groq:openai/gpt-oss-120b | 2.0 s |
| CP-01 | right | groq:openai/gpt-oss-120b | 2.2 s |
| CP-02 | right | groq:openai/gpt-oss-120b | 2.6 s |
| CP-03 | right | groq:openai/gpt-oss-120b | 1.8 s |
| CP-04 | not_tested | none (AI busy) | 1.8 s |
| CP-05 | right | groq:openai/gpt-oss-120b | 2.5 s |
| CP-06 | right | groq:openai/gpt-oss-120b | 2.4 s |
| CP-07 | not_tested | none (AI busy) | 1.3 s |
| CP-08 | right | groq:openai/gpt-oss-120b | 2.7 s |
| TRAP-NAV-01 | refused | groq:openai/gpt-oss-120b | 1.7 s |
| TRAP-NAV-02 | refused | groq:openai/gpt-oss-120b | 1.5 s |
| TRAP-NAV-03 | refused | groq:openai/gpt-oss-120b | 1.5 s |
| TRAP-BG-01 | refused | groq:openai/gpt-oss-120b | 2.5 s |
| TRAP-BG-02 | refused | groq:openai/gpt-oss-120b | 1.6 s |
| TRAP-BG-03 | refused | groq:openai/gpt-oss-120b | 1.8 s |
| TRAP-CP-01 | refused | groq:openai/gpt-oss-120b | 1.5 s |
| TRAP-CP-02 | refused | groq:openai/gpt-oss-120b | 1.6 s |

### Failed questions

- **NAV-05** (missed) expected nav_rules.pdf p.106: How long is a prolonged blast under the Inland Rules?  
  Reason: proof:quote_not_on_page (nav_rules.pdf p.106)  
  Shown: Not in this document  
  AI calls: gemini:gemini-3.1-flash-lite error 0.4 s -> groq:openai/gpt-oss-120b ok 1.1 s
- **NAV-07** (missed) expected nav_rules.pdf p.107|108: When power-driven vessels in sight of one another manoeuvre, what does one short blast mean under the International Rules and under the Inland Rules?  
  Reason: llm_not_found  
  Shown: Not in this document  
  AI calls: gemini:gemini-3.1-flash-lite error 0.4 s -> groq:openai/gpt-oss-120b ok 1.7 s
- **NAV-08** (wrong) expected nav_rules.pdf p.107|108: What light may supplement manoeuvring whistle signals and what is its minimum range under the International and Inland Rules?  
  Reason: numbers differ: expected ['1', '2', '5'], shown ['2', '5']  
  Shown: "All‑round white light, minimum range 5 miles (International) and all‑round white or yellow light, minimum range 2 miles (Inland)." from nav_rules.pdf p.107 (—INTERNATIONAL— Sound and Light Signals Rule 34 Maneuvering ...); nav_rules.pdf p.108 (—INLAND— Sound and Light Signals Rule 34 Maneuvering and War...)  
  AI calls: gemini:gemini-3.1-flash-lite error 0.4 s -> groq:openai/gpt-oss-120b ok 2.1 s
- **NAV-09** (missed) expected nav_rules.pdf p.15|16: Do both the International and Inland Rules define a vessel constrained by her draft?  
  Reason: llm_not_found  
  Shown: Not in this document  
  AI calls: gemini:gemini-3.1-flash-lite error 0.4 s -> groq:openai/gpt-oss-120b ok 0.8 s
- **NAV-10** (wrong) expected nav_rules.pdf p.45: How far away must the top white light of a big ship (50 m or longer) be visible under the International Rules?  
  Reason: numbers differ: expected ['6'], shown ['3']  
  Shown: "3 miles" from nav_rules.pdf p.45 (—INTERNATIONAL— Lights and Shapes Rule 22 Visibility of Ligh...)  
  AI calls: gemini:gemini-3.1-flash-lite error 0.5 s -> groq:openai/gpt-oss-120b ok 1.3 s
- **NAV-11** (missed) expected nav_rules.pdf p.109: What horn signal do I give under the International Rules if I do not understand what the other ship is doing?  
  Reason: proof:off_topic (quote has none of the question's words: the vessel in doubt shall immediately indicate such doubt by)  
  Shown: Not in this document  
  AI calls: gemini:gemini-3.1-flash-lite error 0.3 s -> groq:openai/gpt-oss-120b ok 1.2 s
- **BG-03** (wrong) expected boaters_guide.pdf p.16: What conditions must pyrotechnic visual distress signals meet?  
  Reason: numbers differ: expected [], shown ['42']  
  Shown: "Pyrotechnic visual distress signals must be U.S. Coast Guard-approved, not expired, in serviceable condition, and readily accessible. Check the expira..." from boaters_guide.pdf p.16 (Pyrotechnic Devices)  
  AI calls: gemini:gemini-3.1-flash-lite error 0.3 s -> groq:openai/gpt-oss-120b ok 1.2 s
- **BG-06** (missed) expected boaters_guide.pdf p.26: What size of oil discharge placard must vessels 26 feet and greater in length with machinery spaces display?  
  Reason: proof:off_topic (question numbers not in the quote: 26)  
  Shown: Not in this document  
  AI calls: gemini:gemini-3.1-flash-lite error 0.6 s -> groq:openai/gpt-oss-120b ok 1.2 s
- **BG-08** (missed) expected boaters_guide.pdf p.9: How tall do the numbers on the side of my boat have to be?  
  Reason: proof:off_topic (quote has none of the question's words: Lettering must be in plain, vertical block characters of not)  
  Shown: Not in this document  
  AI calls: gemini:gemini-3.1-flash-lite error 0.4 s -> groq:openai/gpt-oss-120b ok 1.0 s
- **CP-04** (not_tested) expected coast_pilot4_ch1.pdf p.2: How long is a nautical mile?  
  Reason: ai_busy (gemini:gemini-3.1-flash-lite error 0.6 s -> groq:openai/gpt-oss-120b rate_limit 0.1 s)  
  Shown: The AI is busy right now. Here are the best matching pieces from your document instead.
- **CP-07** (not_tested) expected coast_pilot4_ch1.pdf p.2: Roughly how many yards are in one nautical mile?  
  Reason: ai_busy (gemini:gemini-3.1-flash-lite error 0.4 s -> groq:openai/gpt-oss-120b rate_limit 0.1 s)  
  Shown: The AI is busy right now. Here are the best matching pieces from your document instead.

### All answers shown

- **NAV-01** (right): The term vessel restricted in her ability to maneuver means a vessel which from the nature of her work is restricted in her ability to maneuver as req...  
  Source: nav_rules.pdf p.15 (—INTERNATIONAL— General Rule 3 General Definitions); quote: "The term vessel restricted in her ability to maneuver means a vessel which from the nature of her work is restricted in ..."
- **NAV-02** (right): The word underway means that a vessel is not at anchor, or made fast to the shore, or aground.  
  Source: nav_rules.pdf p.17 (—INTERNATIONAL— General Rule 3—CONTINUED); quote: "(i) The word underway means that a vessel is not at anchor, or made fast to the shore, or aground."
- **NAV-03** (right): at least five short and rapid blasts on the whistle  
  Source: nav_rules.pdf p.109 (—INTERNATIONAL— Sound and Light Signals Rule 34—CONTINUED); quote: "(d) When vessels in sight of one another are approaching each other and from any cause either vessel fails to understand..."
- **NAV-04** (right): 6 miles  
  Source: nav_rules.pdf p.45 (—INTERNATIONAL— Lights and Shapes Rule 22 Visibility of Ligh...); quote: "In vessels of 50 meters or more in length: − a masthead light, 6 miles;"
- **NAV-06** (right): two prolonged blasts in succession at intervals of not more than 2 minutes, with about 2 seconds between them.  
  Source: nav_rules.pdf p.111 (—INTERNATIONAL— Sound and Light Signals Rule 35 Sound Signal...); quote: "A power-driven vessel underway but stopped and making no way through the water shall sound at intervals of not more than..."
- **NAV-08** (wrong): All‑round white light, minimum range 5 miles (International) and all‑round white or yellow light, minimum range 2 miles (Inland).  
  Source: nav_rules.pdf p.107 (—INTERNATIONAL— Sound and Light Signals Rule 34 Maneuvering ...); nav_rules.pdf p.108 (—INLAND— Sound and Light Signals Rule 34 Maneuvering and War...); quote: "(iii) the light used for this signal shall, if fitted, be an all-round white light, visible at a minimum range of 5 mile..." | "(iii) The light used for this signal shall, if fitted, be one all-round white or yellow light, visible at a minimum rang..."
- **NAV-10** (wrong): 3 miles  
  Source: nav_rules.pdf p.45 (—INTERNATIONAL— Lights and Shapes Rule 22 Visibility of Ligh...); quote: "In vessels of 50 meters or more in length: − a masthead light, 6 miles; − a sidelight, 3 miles; − a sternlight, 3 miles;..."
- **NAV-12** (right): 70-200 Hz  
  Source: nav_rules.pdf p.137 (—INTERNATIONAL— Annex III Technical Details of Sound Signal ...); quote: "70-200 Hz, for a vessel 200 meters or more in length;"
- **NAV-13** (right): A high intensity white light flashing at regular intervals from 50 to 70 times per minute  
  Source: nav_rules.pdf p.116 (—INLAND— Sound and Light Signals Rule 37 Distress Signals); quote: "A high intensity white light flashing at regular intervals from 50 to 70 times per minute. Inland only."
- **BG-01** (right): anchors, paddles, rearview mirrors, diver/ski flags  
  Source: boaters_guide.pdf p.12 (Equipment Requirements); quote: "The Coast Guard does not regulate anchors, paddles, rearview mirrors, or diver/ski flags."
- **BG-02** (right): Mark the name and hailing port of the vessel together in one place on the hull (usually on the stern).  
  Source: boaters_guide.pdf p.10 (); quote: "Mark the name and hailing port of the vessel together in one place on the hull (usually on the stern)."
- **BG-03** (wrong): Pyrotechnic visual distress signals must be U.S. Coast Guard-approved, not expired, in serviceable condition, and readily accessible. Check the expira...  
  Source: boaters_guide.pdf p.16 (Pyrotechnic Devices); quote: "Pyrotechnic visual distress signals must be U.S. Coast Guard-approved, not expired, in serviceable condition, and readil..."
- **BG-04** (right): The letters and numbers must be at least 3 inches high.  
  Source: boaters_guide.pdf p.9 (Display of Numbers); quote: "Lettering must be in plain, vertical block characters of not less than 3 inches in height."
- **BG-05** (right): They expire 42 months after the date of manufacture.  
  Source: boaters_guide.pdf p.16 (Pyrotechnic Devices); quote: "Check the expiration date (42 months after the date of manufacture)."
- **BG-07** (right): 42 months after the date of manufacture  
  Source: boaters_guide.pdf p.16 (Pyrotechnic Devices); quote: "Check the expiration date (42 months after the date of manufacture)."
- **CP-01** (right): The controlling depth is the least known depth of a channel as determined by hydrographic surveys and restricts the safe use of the channel to drafts ...  
  Source: coast_pilot4_ch1.pdf p.2 (Depths); quote: "(26) The controlling depth is the least known depth of a channel as determined by hydrographic surveys and restricts the..."
- **CP-02** (right): Squat denotes a change in trim of a ship underway, relative to her trim when stopped; it usually causes the stern of a vessel to sit deeper in the wat...  
  Source: coast_pilot4_ch1.pdf p.2 (Under-keel clearances); quote: "(36) Squat denotes a change in trim of a ship underway, relative to her trim when stopped. It usually causes the stern o..."
- **CP-03** (right): Vertical clearances of bridges and overhead cables are given in feet above mean high water unless otherwise stated.  
  Source: coast_pilot4_ch1.pdf p.1 (Bridges and Cables); quote: "Vertical clearances of bridges and overhead cables are in feet above mean high water unless otherwise stated; clearances..."
- **CP-05** (right): Settlement is appreciable when the depth is less than seven times the draft of the ship.  
  Source: coast_pilot4_ch1.pdf p.2 (Under-keel clearances); quote: "Settlement is appreciable when the depth is less than seven times the draft of the ship and increases as the depth decre..."
- **CP-06** (right): Ships of length 20m or greater  
  Source: coast_pilot4_ch1.pdf p.15 (U.S. VHF Channel Information Ship Frequency (MHz) New Old Ch...); quote: "All ships of length 20m or greater are required to guard VHF channel 13, in addition to VHF channel 16, when operating w..."
- **CP-08** (right): Squat denotes a change in trim of a ship underway, relative to her trim when stopped. It usually causes the stern of a vessel to sit deeper in the wat...  
  Source: coast_pilot4_ch1.pdf p.2 (Under-keel clearances); quote: "(36) Squat denotes a change in trim of a ship underway, relative to her trim when stopped. It usually causes the stern o..."
<!-- END phase4-answers -->
