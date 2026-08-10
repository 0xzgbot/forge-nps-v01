import pytest
from agents.auditor.continuity_auditor import ContinuityAuditor, ErrorCategory

@pytest.mark.asyncio
async def test_audit_asset_structure():
    """Verify that the single asset audit contains all new required fields."""
    # Use a non-existent lore file but it's okay as we mock/simulate behavior
    auditor = ContinuityAuditor("non_existent.json")
    
    # Test consistent case
    res_ok = await auditor.audit_asset("A beautiful sunset over the city", "shot_001")
    assert res_ok["is_consistent"] is True
    assert "confidence_score" in res_ok
    assert "error_category" in res_ok
    assert "mismatch_report" in res_ok
    assert "remediation_prompt" in res_ok
    assert "affected_anchors" in res_ok
    assert res_ok["error_category"] == ErrorCategory.NONE.value

    # Test inconsistent case (Photometric)
    res_err = await auditor.audit_asset("A man with red eyes", "shot_002")
    assert res_err["is_consistent"] is False
    assert res_err["error_category"] == ErrorCategory.PHOTOMETRIC.value
    assert len(res_err["affected_anchors"]) > 0
    assert "remediation_prompt" in res_err

@pytest.mark.asyncio
async def test_audit_batch_individual_failures():
    """Verify that audit_batch correctly identifies individual shot failures."""
    auditor = ContinuityAuditor("non_existent.json")
    shots = [
        {"id": "shot_1", "description": "Perfect shot"},
        {"id": "shot_2", "description": "An extra limb is visible"}, # Anatomical error
        {"id": "shot_3", "description": "A man with red eyes"}          # Photometric error
    ]
    director_schema = {}
    
    summary = await auditor.audit_batch(shots, director_schema)
    
    assert summary["total_shots"] == 3
    assert summary["consistent_count"] == 1
    assert summary["inconsistent_count"] == 2
    # Verify individual results in the summary
    results = {r["shot_id"]: r for r in summary["shot_results"]}
    assert results["shot_2"]["error_category"] == ErrorCategory.ANATOMICAL.value
    assert results["shot_3"]["error_category"] == ErrorCategory.PHOTOMETRIC.value

@pytest.mark.asyncio
async def test_audit_batch_global_warning():
    """Verify that audit_batch generates a global_consistency_warning for systemic failures."""
    auditor = ContinuityAuditor("non_existent.json")
    # 3 shots, 2 have "red eyes" -> > 50% failure in Photometric category
    shots = [
        {"id": "shot_1", "description": "A man with red eyes"},
        {"id": "shot_2", "description": "A man with red eyes"},
        {"id": "shot_3", "description": "A perfect shot"}
    ]
    director_schema = {}
    
    summary = await auditor.audit_batch(shots, director_schema)
    
    assert summary["global_consistency_warning"] is not None
    assert "Photometric" in summary["global_consistency_warning"]
    assert summary["systemic_error_category"] == ErrorCategory.PHOTOMETRIC.value

if __name__ == "__main__":
    # Allow running tests directly via python
    pytest.main([__file__])
