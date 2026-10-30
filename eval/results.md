# Results

## Phase 3 baseline: keyword search (BM25), no AI

- Documents in one index: boaters_guide.pdf, coast_pilot4_ch1.pdf, nav_rules.pdf (2149 pieces)
- Threshold `BASELINE_MIN_SCORE` = **11.5** (sweep recommends 11.5; rule below)
- Reading + chunking the PDFs: 22.0 s (once, at upload). Average search time per question: **2.2 ms**

| Measure | Result |
|---|---|
| Right doc + page, top 1 | 17/29 (59%) |
| Right doc + page, top 3 | 23/29 (79%) |
| Exact answer in top-1 piece (all numbers + key words) | 15/29 (52%) |
| Traps correctly "Not in this document" | 7/8 (88%) |
| **Wrong: answered from a wrong page** (must be 0 in Phase 4) | **8** |
| **Traps answered** (also wrong) | **1** |
| Missed: real question but said "Not in this document" | 4 |

Compare rows count as right page if the top piece is on either of their two pages. "Exact answer" is strict: a compare answer needs both pages, so it cannot be in one piece.

### Per document

| Document | Questions | Right page top 1 | Right page top 3 | Exact answer top 1 | Wrong | Missed |
|---|---|---|---|---|---|---|
| boaters_guide.pdf | 8 | 5/8 (62%) | 7/8 (88%) | 5/8 (62%) | 2 | 1 |
| coast_pilot4_ch1.pdf | 8 | 5/8 (62%) | 7/8 (88%) | 5/8 (62%) | 0 | 3 |
| nav_rules.pdf | 13 | 7/13 (54%) | 9/13 (69%) | 5/13 (38%) | 6 | 0 |

### Per type

| Type | Questions | Right page top 1 | Right page top 3 | Exact answer top 1 | Wrong | Missed |
|---|---|---|---|---|---|---|
| annex | 2 | 1/2 (50%) | 2/2 (100%) | 1/2 (50%) | 1 | 0 |
| compare | 3 | 2/3 (67%) | 2/3 (67%) | 0/3 (0%) | 1 | 0 |
| fact | 9 | 6/9 (67%) | 9/9 (100%) | 7/9 (78%) | 2 | 1 |
| number | 9 | 6/9 (67%) | 7/9 (78%) | 5/9 (56%) | 2 | 1 |
| paraphrase | 6 | 2/6 (33%) | 3/6 (50%) | 2/6 (33%) | 2 | 2 |

## Threshold

If the best BM25 score is below the threshold, the answer is "Not in this document".

- **Too high:** real questions get "Not in this document" (missed answers).
- **Too low:** trap questions get an answer from some unrelated piece (a wrong answer, worse).

Rule, fixed before looking at single questions: pick the threshold with the most correct outcomes (right page + traps refused); on a tie pick the higher one ("never guess"). With only 29 questions and 8 traps this is a first estimate, not a final value.

| Threshold | Right | Wrong | Missed | Traps refused | Traps answered | Correct total |
|---|---|---|---|---|---|---|
| 0.0 | 18 | 11 | 0 | 1 | 7 | 19 |
| 0.5 | 18 | 11 | 0 | 1 | 7 | 19 |
| 1.0 | 18 | 11 | 0 | 1 | 7 | 19 |
| 1.5 | 18 | 11 | 0 | 1 | 7 | 19 |
| 2.0 | 18 | 11 | 0 | 1 | 7 | 19 |
| 2.5 | 18 | 11 | 0 | 1 | 7 | 19 |
| 3.0 | 18 | 11 | 0 | 1 | 7 | 19 |
| 3.5 | 18 | 11 | 0 | 1 | 7 | 19 |
| 4.0 | 18 | 11 | 0 | 1 | 7 | 19 |
| 4.5 | 18 | 11 | 0 | 1 | 7 | 19 |
| 5.0 | 18 | 11 | 0 | 1 | 7 | 19 |
| 5.5 | 18 | 11 | 0 | 2 | 6 | 20 |
| 6.0 | 18 | 11 | 0 | 3 | 5 | 21 |
| 6.5 | 18 | 11 | 0 | 3 | 5 | 21 |
| 7.0 | 18 | 11 | 0 | 3 | 5 | 21 |
| 7.5 | 18 | 11 | 0 | 3 | 5 | 21 |
| 8.0 | 17 | 11 | 1 | 3 | 5 | 20 |
| 8.5 | 17 | 10 | 2 | 3 | 5 | 20 |
| 9.0 | 17 | 10 | 2 | 5 | 3 | 22 |
| 9.5 | 17 | 10 | 2 | 5 | 3 | 22 |
| 10.0 | 17 | 10 | 2 | 5 | 3 | 22 |
| 10.5 | 17 | 9 | 3 | 6 | 2 | 23 |
| 11.0 | 17 | 9 | 3 | 6 | 2 | 23 |
| 11.5 | 17 | 8 | 4 | 7 | 1 | 24 ← chosen |
| 12.0 | 16 | 8 | 5 | 7 | 1 | 23 |
| 12.5 | 16 | 7 | 6 | 7 | 1 | 23 |
| 13.0 | 16 | 7 | 6 | 7 | 1 | 23 |
| 13.5 | 16 | 7 | 6 | 7 | 1 | 23 |
| 14.0 | 15 | 7 | 7 | 7 | 1 | 22 |
| 14.5 | 14 | 6 | 9 | 7 | 1 | 21 |
| 15.0 | 14 | 5 | 10 | 7 | 1 | 21 |
| 15.5 | 13 | 5 | 11 | 7 | 1 | 20 |
| 16.0 | 13 | 5 | 11 | 8 | 0 | 21 |
| 16.5 | 13 | 5 | 11 | 8 | 0 | 21 |
| 17.0 | 13 | 5 | 11 | 8 | 0 | 21 |
| 17.5 | 12 | 5 | 12 | 8 | 0 | 20 |
| 18.0 | 12 | 5 | 12 | 8 | 0 | 20 |
| 18.5 | 12 | 4 | 13 | 8 | 0 | 20 |
| 19.0 | 12 | 4 | 13 | 8 | 0 | 20 |
| 19.5 | 11 | 3 | 15 | 8 | 0 | 19 |
| 20.0 | 10 | 3 | 16 | 8 | 0 | 18 |

## Failed questions

- **NAV-03** (wrong) expected nav_rules.pdf p.109: Under the International Rules, what signal must a vessel give when it is in doubt about the intentions or actions of an approaching vessel?  
  Returned: answered; top 1: coast_pilot4_ch1.pdf p.22, score 26.8: "(313) Navigation Rules, International-Inland, Rule 34(d), states that when vessels in sight of one another are approachi..."; also: nav_rules.pdf p.109 (26.5), nav_rules.pdf p.110 (25.3)
- **NAV-05** (wrong) expected nav_rules.pdf p.106: How long is a prolonged blast under the Inland Rules?  
  Returned: answered; top 1: nav_rules.pdf p.110, score 14.5: "(e) A vessel nearing a bend or an area of a channel or fairway where other vessels may be obscured by an intervening obs..."; also: nav_rules.pdf p.105 (13.8), nav_rules.pdf p.110 (13.6)
- **NAV-09** (wrong) expected nav_rules.pdf p.15|16: Do both the International and Inland Rules define a vessel constrained by her draft?  
  Returned: answered; top 1: nav_rules.pdf p.37, score 18.1: "(ii) A vessel constrained by her draft shall navigate with particular caution having full regard to her special conditio..."; also: nav_rules.pdf p.95 (17.6), nav_rules.pdf p.37 (16.4)
- **NAV-10** (wrong) expected nav_rules.pdf p.45: How far away must the top white light of a big ship (50 m or longer) be visible under the International Rules?  
  Returned: answered; top 1: nav_rules.pdf p.143, score 14.4: "(m) a ship-to-shore distress alert transmitted by the ship’s Inmarsat or other mobile satellite service provider ship ea..."; also: nav_rules.pdf p.107 (13.5), nav_rules.pdf p.125 (13.2)
- **NAV-11** (wrong) expected nav_rules.pdf p.109: What horn signal do I give under the International Rules if I do not understand what the other ship is doing?  
  Returned: answered; top 1: nav_rules.pdf p.163, score 12.2: "(d) An east-west line (latitude 30°14.7’ N.) drawn between the westernmost extremity of Horn Island to the easternmost e..."; also: nav_rules.pdf p.113 (11.9), coast_pilot4_ch1.pdf p.22 (11.0)
- **NAV-13** (wrong) expected nav_rules.pdf p.144: Under the Inland Rules, which flashing white light is a distress signal?  
  Returned: answered; top 1: nav_rules.pdf p.116, score 19.3: "§83.37 When a vessel is in distress and requires assistance she shall use or exhibit the signals described in Annex IV o..."; also: nav_rules.pdf p.144 (16.5), boaters_guide.pdf p.18 (14.5)
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

## Right page, but exact answer not in the top-1 piece

- **NAV-04** expected "6 miles"  
  Top-1 piece: "(b) In vessels of 12 meters or more in length but less than 50 meters in length: − a masthead light, 5 miles; except that where the length of the vessel is less..."
- **NAV-07** expected "International: “I am altering my course to starboard”. Inland: “I intend to leave you on my port side”."  
  Top-1 piece: "(a) When vessels are in sight of one another, a power-driven vessel underway, when maneuvering as authorized or required by these Rules, shall indicate that man..."
- **NAV-08** expected "International: an all-round white light visible at a minimum range of 5 miles. Inland: one all-round white or yellow light visible at a minimum range of 2 miles."  
  Top-1 piece: "(b) A vessel may supplement the whistle signals prescribed in paragraph (a) of this Rule by light signals:"
- **NAV-12** expected "Between 70-200 Hz."  
  Top-1 piece: "(a) Frequencies and range of audibility The fundamental frequency of the signal shall lie within the range 70-700 Hz. The range of audibility of the signal from..."
