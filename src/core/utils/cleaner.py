"""Module to clean and extract relevant fact-check results."""

import logging

logger = logging.getLogger(__name__)


def clean_facts(json_data: dict | None) -> list:
    """Extract relevant fact-check results with dynamic evidence balancing."""
    cleaned_results: list[dict] = []

    if json_data is None:
        return cleaned_results

    try:
        items_to_process = []
        if (
            "collection" in json_data
            and json_data.get("collection") == "stance_detection"
        ):
            items_to_process = [json_data]
        else:
            items_to_process = json_data.get("text", [])
            if items_to_process is None:
                return cleaned_results

        for item in items_to_process:
            if item is None:
                continue

            evidence_list = item.get("evidence", [])
            if not evidence_list:
                continue

            claim_text = item.get("claim", "")
            if claim_text is not None:
                claim_text = claim_text.replace('"', "'")

            summary = item.get("summary", "")
            if summary is not None:
                if isinstance(summary, list):
                    summary = " ".join(str(s) for s in summary if s is not None)
                    if summary:
                        summary = summary.replace('"', "'")
                elif isinstance(summary, str):
                    summary = summary.replace('"', "'")

            fix = item.get("fix", "")
            if fix is not None:
                fix = fix.replace('"', "'")

            final_verdict = "Uncertain"
            if item.get("finalPrediction") is not None:
                final_verdict = (
                    "Incorrect"
                    if item.get("finalPrediction") == 0
                    else "Correct"
                )

            confidence = (
                round((1 - (item.get("finalScore") or 0)) * 100, 2)
                if final_verdict == "Incorrect"
                else round((item.get("finalScore") or 0) * 100, 2)
            )

            supporting_evidence = []
            refuting_evidence = []

            for evidence in evidence_list:
                if evidence is None:
                    continue

                label = evidence.get("labelDescription", "")
                if label not in ["SUPPORTS", "REFUTES"]:
                    continue

                sim_score = evidence.get("simScore", 0)
                evidence_snippet = ""
                if sim_score > 0.5:
                    snippet = evidence.get("evidenceSnippet", "")
                    if snippet is not None:
                        evidence_snippet = (
                            snippet[:1000] + "..."
                            if len(snippet) > 1000
                            else snippet
                        )

                domain_reliability_obj = (
                    evidence.get("domain_reliability", {}) or {}
                )
                reliability = domain_reliability_obj.get(
                    "Reliability", "Unknown"
                )

                evidence_entry = {
                    "labelDescription": label,
                    "domain_name": evidence.get("domainName", ""),
                    "domainReliability": reliability,
                    "url": evidence.get("url", ""),
                    "evidenceSnippet": evidence_snippet,
                }

                if label == "SUPPORTS":
                    supporting_evidence.append(evidence_entry)
                else:
                    refuting_evidence.append(evidence_entry)

            if not summary and not fix:
                cleaned_results.append(
                    {
                        "strict_formatting": f"""
                        IMPORTANT:
                        DO NOT PROVIDE ANY ANALYSIS OR ELABORATION ON THE CLAIM.
                        YOU MUST RESPOND IDENTICAL TO THE IDENTICAL PART,
                        AND YOU MUST RESPOND NATURALLY TO THE NATURAL PART:

                        --- IDENTICAL ---
                        Claim: {claim_text}
                        Verdict: {final_verdict} ({confidence}% confidence)
                        --- IDENTICAL ---

                        --- NATURAL ---
                        URL AND EVIDENCE SNIPPET SUMMARY ONLY (MAX 3):
                        - Supporting Evidence: {supporting_evidence} sources
                        - Refuting Evidence: {refuting_evidence} sources

                        End with an encouraging ending
                        --- NATURAL ---
                        """,
                    }
                )
            else:
                cleaned_results.append(
                    {
                        "claim": claim_text,
                        "verdict": final_verdict,
                        "confidence_percentage": confidence,
                        "summary": summary,
                        "fix": fix,
                        "supporting_evidence": supporting_evidence,
                        "refuting_evidence": refuting_evidence,
                    }
                )

        logger.info(cleaned_results)
        return cleaned_results

    except Exception as e:
        logger.error(f"Error cleaning facts: {str(e)}")
        return []
