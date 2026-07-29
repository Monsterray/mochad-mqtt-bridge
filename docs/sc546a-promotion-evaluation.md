# SC546A Promotion Evaluation

Decision date: 2026-07-29

Decision: **remain experimental**

The project lead previously required the SC546A named profile to remain
experimental until its model claims have both deterministic fixture evidence
and reviewed physical evidence. This review confirms `fixture_verified=true`
and `hardware_verified=false`; the profile therefore does not meet the
promotion rules.

## Source Record

| Field | Value |
|---|---|
| Artifact | `SC546A.pdf` |
| Model visible in artifact | Remote Chime, Model SC546A |
| Source type | Manufacturer manual |
| Publisher | X10 Wireless Technology, Inc. |
| Revision visible in artifact | SC546A-6/13 |
| Pages | 2 |
| SHA-256 | `84edf836c1ca3dc174c5703cb458f599fb4ab8f20db3f458aeedde1af77d9645` |
| Reviewed locator | PDF page 1, Installation and Operating Instructions |
| Upstream URL | <https://cdn.shopify.com/s/files/1/2279/4329/files/SC546A.pdf> |

The reviewed workspace artifact is tracked only in the shared research cache,
not in this repository. The manual is copyrighted source material; this record
contains an independent summary and no copied diagram or extended passage. A
different legacy PHH02 artifact must not be treated as SC546A evidence.

## Claim Matrix

| Claim | Evidence | Confidence | Fixture | Hardware |
|---|---|---|---|---|
| The SC546A is a plug-in X10 remote chime with House and Unit dials. | Manufacturer manual, page 1, steps 1-3 | confirmed | true | false |
| Matching House and Unit addressing is required. | Manufacturer manual, page 1, steps 1, 2, and 4 | confirmed | true | false |
| A motion sensor may send through a TM751, which retransmits over house wiring to the chime. | Manufacturer manual, page 1, steps 2 and 4 | confirmed | true | false |
| The bridge represents the device as a Home Assistant button with no retained state. | Project capability policy and deterministic discovery/state tests | confirmed | true | false |
| Every explicit bridge `ON` request reaches Mochad and remains unconfirmed. | Deterministic command fixture and bridge tests | confirmed | true | false |
| A CM19A RF `ON` through a TM751 physically activates the SC546A. | Manual supports the general controller/transceiver path, but not this exact chain | well_supported | true | false |
| Two intentional `ON` requests produce two physical chimes. | Software preserves both requests; no complete physical observation is recorded | unverified | true | false |
| Physical `OFF` is ignored. | Not stated by the reviewed manual | unverified | false | false |
| A wrong Unit or House setting does not chime. | Address matching is documented, but the negative outcomes are not recorded | inferred | false | false |

`fixture=true` means only that deterministic software behavior is checked. It
does not mean the physical chime acted.

## Deterministic Fixture

The machine-readable evaluation fixture is
[`tests/fixtures/device_profiles/sc546a_promotion_evaluation.json`](../tests/fixtures/device_profiles/sc546a_promotion_evaluation.json).
The existing command fixture sends two explicit `ON` requests. Tests require:

- two Mochad command writes;
- Home Assistant button discovery;
- no retained state publication;
- an unconfirmed transmission event for each request;
- rejection or omission of `OFF`, `DIM`, and `BRIGHT`;
- diagnostics reporting `experimental`, `fixture_verified=true`, and
  `hardware_verified=false`.

## Hardware Procedure

Physical validation remains approval-gated. Use the workspace hardware lock,
the restricted lab account, isolated TCP and MQTT resources, disabled Home
Assistant discovery, and X10 house code `D` only.

1. Record the exact bridge, Redux, and validation-tool SHAs and confirm clean
   trees.
2. Acquire `/run/lock/x10-hardware.lock`.
3. Display every proposed transmission and obtain explicit human approval.
4. Set the TM751 and SC546A to `D1`.
5. Send one `rf D1 on`; record Redux transmission evidence and human chime
   observation separately.
6. Send two intentional `rf D1 on` commands; record the number of audible
   chimes.
7. Send `rf D1 off`; record whether any chime occurs.
8. With the SC546A still at `D1`, send `rf D2 on`; record whether any chime
   occurs.
9. Set the SC546A to `E1`, send only the permitted development command
   `rf D1 on`, and record whether any chime occurs. Do not transmit on house
   code `E`.
10. Restore the device dials, release the lock, and save the evidence without
    upgrading automated transport results into physical confirmation.

Until all observable outcomes are recorded against exact SHAs and reviewed by
the project lead, each physical result is `HARDWARE REQUIRED`.

## Promotion Decision

The named profile remains `experimental` and continues to require explicit
opt-in. This decision preserves the existing Home Assistant button, repeated
`ON`, non-retained state, and unconfirmed transmission behavior. Promotion to
`candidate` or `verified` requires a new review; fixture success alone is
insufficient.
