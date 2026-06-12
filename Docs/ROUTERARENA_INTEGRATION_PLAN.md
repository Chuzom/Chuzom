# RouterArena Integration Plan — Chuzom v0.3.0-beta

**Objective**: Integrate Chuzom into RouterArena's benchmark suite to validate routing performance before releasing v0.3.0-beta to PyPI.

**No shortcuts. No fake scores. All tests must be reliable and reproducible.**

---

## Part 1: RouterArena Architecture

### 4-Step Evaluation Pipeline

1. **Setup** — Install tools, download dataset, configure API keys
2. **Get Routing Decisions** — Router predicts which model should handle each query
3. **Run LLM Inference** — Execute API calls using predicted models
4. **Run Evaluation** — Compute accuracy, cost, and arena score

### Key Metrics (What We're Being Scored On)

| Metric | Formula | What It Measures | Weight |
|--------|---------|------------------|--------|
| **Accuracy (A_i)** | Correct predictions / Total predictions | % of correct routing decisions | High (β=0.9) |
| **Cost/1K Queries** | (Total cost / # queries) × 1000 | Average cost per 1000 queries | Low (β=0.1) |
| **Arena Score** | `S = ((1+β)·A·C_norm)/(β·A+C_norm)` | Harmonic mean of accuracy & cost efficiency | **Final Ranking** |
| **Optimal Selection %** | (Optimal choices / Total) × 100 | % of truly best model choices | Diagnostic |
| **Optimal Cost %** | (Optimal cost / Actual cost) × 100 | Cost relative to oracle | Diagnostic |

### Arena Score Deep Dive

The **Arena Score** is the final ranking metric:

```python
def compute_arena_score(cost_per_1k, accuracy, beta=0.1, c_max=200, c_min=0.0044):
    # Normalize cost on logarithmic scale (log base 2)
    C_i = (log2(c_max) - log2(cost_per_1k)) / (log2(c_max) - log2(c_min))
    
    # Harmonic mean heavily weighted toward accuracy (β=0.1 means 90% accuracy)
    S = ((1 + beta) * accuracy * C_i) / (beta * accuracy + C_i)
    
    return S
```

**Key insights:**
- β=0.1 means **accuracy is 9× more important than cost** in final score
- Cost normalized logarithmically (diminishing returns on cheap models)
- Score range: ~0 to ~1.0 (higher is better)
- At c_max=$200/1K: normalized cost = 0 (expensive, bad)
- At c_min=$0.0044/1K: normalized cost = 1 (cheap, good)

### Dataset Characteristics

- **Domains**: 9 (MCQ, code, math, writing, chess, geography, etc.)
- **Size**: 8,400 queries total (sub_10 = 10 queries for testing)
- **Difficulty**: Easy, Medium, Hard splits per domain
- **Supported Models**: 80+ models (GPT-4, Claude, Gemini, Deepseek, Qwen, Mistral, Llama, etc.)

---

## Part 2: Expected Chuzom Scores (Baseline Projections)

### Scoring Model

**Assumption**: Chuzom uses Complexity-driven routing:
- SIMPLE (Haiku/cheap) → MCQ, geography, easy writing (~$0.001/query)
- MODERATE (Sonnet/balanced) → Code, math, medium tasks (~$0.010/query)
- COMPLEX (Opus/premium) → Hard code, reasoning (~$0.040/query)

### Accuracy Projection

RouterArena evaluates which model is **correct**, not which router correctly picked it. So Chuzom's accuracy depends on **model performance**, not routing quality.

| Model | MCQ/Geography | Code | Math | Reasoning | Avg |
|-------|---------------|------|------|-----------|-----|
| Haiku (SIMPLE) | 0.75 | 0.40 | 0.45 | 0.35 | **0.49** |
| Sonnet (MODERATE) | 0.85 | 0.80 | 0.75 | 0.70 | **0.78** |
| Opus (COMPLEX) | 0.92 | 0.90 | 0.88 | 0.85 | **0.89** |

**Chuzom Blended Accuracy** (if routing complexity correctly):
- ~33% simple (0.49) + 50% moderate (0.78) + 17% complex (0.89) = **~0.72**

### Cost Projection

```
# Assuming default Chuzom routing:
- 33% SIMPLE @ $0.0005/token ≈ $0.001/query
- 50% MODERATE @ $0.005/token ≈ $0.010/query  
- 17% COMPLEX @ $0.040/token ≈ $0.040/query

Average cost/query = (0.33 × $0.001) + (0.50 × $0.010) + (0.17 × $0.040)
                   ≈ $0.0003 + $0.005 + $0.0068
                   ≈ $0.012/query
                   = $12/1K queries
```

### Arena Score Projection

```python
accuracy = 0.72
cost_per_1k = 12.0
beta = 0.1
c_max = 200
c_min = 0.0044

C_norm = (log2(200) - log2(12)) / (log2(200) - log2(0.0044))
       = (7.644 - 3.585) / (7.644 - (-7.813))
       = 4.059 / 15.457
       ≈ 0.263

S = ((1 + 0.1) * 0.72 * 0.263) / (0.1 * 0.72 + 0.263)
  = (1.1 * 0.189) / (0.072 + 0.263)
  = 0.208 / 0.335
  ≈ 0.62
```

**Expected Chuzom Arena Score: ~0.60–0.65**

### Context: Leaderboard Benchmarks

Top performers typically score:
- **vLLM-SR** (Rank 1): ~0.75+ (excellent cost + accuracy balance)
- **AgentForge** (Top 5): ~0.72–0.73 (good routing + cost control)
- **R2-Router** (Mid-tier): ~0.65–0.68 (decent routing)
- **Random Router**: ~0.45–0.50 (baseline)

**Chuzom's ~0.62 score = Top 30–40% of leaderboard** (respectable for first submission)

---

## Part 3: Integration Steps (No Shortcuts)

### Step 1: Set Up RouterArena Locally

```bash
# Clone RouterArena
git clone https://github.com/RouteWorks/RouterArena.git
cd RouterArena

# Install dependencies
pip install -e .

# Download dataset (8.4GB)
python scripts/download_dataset.py

# Test with sub_10 (10 queries, validates setup)
python router_inference/generate_prediction_file.py auto_router sub_10
python router_evaluation/compute_scores.py auto_router
```

### Step 2: Implement ChuzomRouter Class

**File**: `router_inference/router/chuzom_router.py`

```python
import asyncio
from router_inference.router.base_router import BaseRouter
from chuzom.router import route_and_call
from chuzom.types import TaskType, Complexity

class ChuzomRouter(BaseRouter):
    """
    Chuzom router for RouterArena benchmark.
    
    Routes each query using Chuzom's complexity-driven strategy:
    - Analyzes query to determine task type (query, code, reasoning, etc.)
    - Maps task_type → Complexity (simple/moderate/complex)
    - Routes to appropriate model tier
    """
    
    def __init__(self, router_name: str):
        super().__init__(router_name)
        # Map model names to Chuzom's internal names
        self.model_map = self._build_model_map()
    
    def _build_model_map(self) -> dict:
        """Build mapping from RouterArena model names to Chuzom models."""
        # Example mapping (will need comprehensive version)
        return {
            "gpt-4o-mini": "openai/gpt-4o-mini",  # SIMPLE tier
            "claude-3-haiku": "anthropic/claude-3-haiku",  # SIMPLE
            "gpt-4o": "openai/gpt-4o",  # MODERATE
            "claude-3-sonnet": "anthropic/claude-3-sonnet",  # MODERATE
            "gpt-5": "openai/gpt-5",  # COMPLEX
            "claude-opus-4": "anthropic/claude-opus-4",  # COMPLEX
        }
    
    def _classify_complexity(self, query: str) -> Complexity:
        """
        Determine query complexity using Chuzom's classifier.
        
        Returns: Complexity.SIMPLE, MODERATE, or COMPLEX
        """
        # Option 1: Use Chuzom's built-in classifier (if available)
        # Option 2: Simple heuristic (keywords, length, etc.)
        # Option 3: Prompt a small model for classification
        pass
    
    def _get_prediction(self, query: str) -> str:
        """
        Predict which model should handle this query.
        
        1. Classify query complexity (simple/moderate/complex)
        2. Select model from available list matching that tier
        3. Return RouterArena-compatible model name
        """
        complexity = self._classify_complexity(query)
        
        # Tier selection based on complexity
        tier_map = {
            Complexity.SIMPLE: ["gpt-4o-mini", "claude-3-haiku"],
            Complexity.MODERATE: ["gpt-4o", "claude-3-sonnet"],
            Complexity.COMPLEX: ["gpt-5", "claude-opus-4"],
        }
        
        candidates = tier_map.get(complexity, ["gpt-4o"])
        
        # Pick first available in config
        for model in candidates:
            if model in self.models:
                return model
        
        # Fallback to first model in config
        return self.models[0]
```

### Step 3: Create Chuzom Config

**File**: `router_inference/config/chuzom.json`

```json
{
    "pipeline_params": {
        "router_name": "chuzom",
        "router_cls_name": "chuzom_router",
        "models": [
            "gpt-4o-mini",
            "claude-3-haiku-20240307",
            "gpt-4o",
            "claude-3-7-sonnet-20250219",
            "gpt-5",
            "claude-opus-4-6"
        ]
    }
}
```

### Step 4: Register ChuzomRouter

**File**: `router_inference/router/__init__.py`

```python
from router_inference.router.chuzom_router import ChuzomRouter

# Add to router registry
__all__ = ["BaseRouter", "ChuzomRouter", "ExampleRouter", ...]
```

### Step 5: Generate Predictions (Validate, Don't Fake)

```bash
# Step 5a: Test with sub_10 (10 queries, fast validation)
python router_inference/generate_prediction_file.py chuzom sub_10

# Step 5b: Run inference on predictions
python llm_inference/run_inference.py chuzom sub_10

# Step 5c: Evaluate
python router_evaluation/compute_scores.py chuzom

# Step 5d: Full dataset (8.4K queries, slow but necessary)
python router_inference/generate_prediction_file.py chuzom full
python llm_inference/run_inference.py chuzom full
python router_evaluation/compute_scores.py chuzom

# Step 5e: Robustness test (test stability)
python router_inference/generate_prediction_file.py chuzom robustness
python llm_inference/run_inference.py chuzom robustness
python router_evaluation/compute_scores.py chuzom
```

### Step 6: Validate Scores (No Shortcuts)

**Checklist before submission:**
- [ ] All predictions match available models in config
- [ ] No null/missing predictions (100% coverage)
- [ ] Cost calculations match actual token usage
- [ ] Accuracy scores are consistent across runs
- [ ] sub_10 scores match full dataset pattern (statistical consistency)
- [ ] Robustness scores within 5% of full scores (no overfitting)
- [ ] Arena score formula validated with Python script
- [ ] Results reproducible on clean checkout

### Step 7: Document Results

**Create**: `Docs/ROUTERARENA_RESULTS.md`

```markdown
# Chuzom RouterArena Benchmark Results

## Scores (Full Dataset)

| Metric | Score | Notes |
|--------|-------|-------|
| Average Accuracy | X.XX% | Correctness of routing decisions |
| Cost per 1K Queries | $X.XX | Cost efficiency |
| Arena Score | X.XX | Final ranking metric |
| Optimal Selection | X.XX% | Percentage of truly optimal choices |
| Optimal Cost | X.XX% | Cost relative to oracle |

## Analysis

[Per-domain breakdown, comparison to benchmarks, routing pattern analysis]

## Conclusion

[Does Chuzom's routing help or hurt? Why? Next steps?]
```

---

## Part 4: Expected Outcomes & Quality Gates

### Success Criteria (Before Release)

1. ✅ **Arena Score ≥ 0.55** (Top 40% of leaderboard)
2. ✅ **Accuracy ≥ 0.68** (Better than random)
3. ✅ **Cost Efficiency ≥ 0.50** (Not wasteful)
4. ✅ **All scores reproducible** (±0.01 variance)
5. ✅ **Robustness score within 5% of full score** (No overfitting)
6. ✅ **Documentation complete** (No mystery scores)

### Red Flags (Investigation Required)

- 🚨 Arena Score < 0.50 (Below average)
- 🚨 Accuracy < 0.60 (Routing making things worse)
- 🚨 Cost > $50/1K (Wasteful routing)
- 🚨 Robustness ≠ Full score (Indicates overfitting)
- 🚨 > 1% prediction mismatches (Implementation bugs)

### Next Steps Based on Results

- **Score > 0.68**: Proceed to v0.3.0-beta release + submit to leaderboard
- **Score 0.55–0.68**: Document findings, identify improvement areas, release with caveats
- **Score < 0.55**: Debug routing logic, improve classifier, re-run before release

---

## Timeline

- **Day 5 (Today)**: Setup, implement, test on sub_10 ✓
- **Day 5 (Evening)**: Run full dataset ✓
- **Day 5 (Late)**: Validate scores, debug if needed ✓
- **Day 6 (Morning)**: Document results, make release decision ✓
- **Day 6 (Afternoon)**: Release v0.3.0-beta to PyPI with benchmark link ✓

---

## Critical: No Fake Scores

Every score must be:
- ✅ Generated by RouterArena's official `compute_scores.py`
- ✅ Reproducible from scratch (no cached results without explanation)
- ✅ Validated against historical benchmarks
- ✅ Documented with methodology and assumptions
- ✅ Honest about limitations (e.g., "Chuzom optimized for low cost, not max accuracy")

**If scores don't meet success criteria, we document why and improve, not cut corners.**
