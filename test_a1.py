from core.routing.architect_router import ArchitectRouter, KernelFactory

router = ArchitectRouter()
result = router.route("high_fidelity_image", {"subject": "test"})

# The test code in INTEGRATION_PLAN says result["kernel"] == "flux_2_dev"
# But my implementation returns 'kernel' as a key and the value is 'flux_2_dev'.
# Let's adjust the implementation or the test. 
# Wait, looking at requirements: Implement ArchitectRouter.
# Requirements for route return in my code:
# return {
#     "status": "success",
#     "kernel": kernel_id,
#     "prompt": ...,
#     "payload": payload
# }
# The test expectation is result["kernel"] == "flux_2_dev". This matches.

assert result["kernel"] == "flux_2_dev"
assert "prompt" in result
print("A1 PASS")
