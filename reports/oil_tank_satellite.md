# Cushing oil tanks from free satellite images (Sentinel-2)

**Verdict: No edge: free 10 m imagery sees fill only faintly, far too noisily to call weekly changes.**

Floating-roof tanks show a crescent of shadow on the roof that grows as the tank empties. We measured that shadow on every cloud-free Sentinel-2 pass over the Cushing tank farm and compared it with EIA's weekly Cushing crude stocks.

| | |
|---|---|
| Cloud-free scenes | 217 (103 before 2023, 114 after) |
| Tanks found | 284, of which 87 showed a fill signal in training |
| All tanks, fill coefficient (t) | -0.00156 (-6.71) |
| Picked tanks, training (t) | -0.00419 (-11.24) |
| Picked tanks, hold-out (t) | -0.00206 (-2.85) |
| Hold-out: estimate vs actual stocks, correlation | 0.14 |
| Hold-out: estimate error, sd (million bbl) | 14.0 |
| Typical EIA weekly move, sd (million bbl) | 1.4 |
| Hold-out: scene-to-scene change vs actual change, correlation (75 pairs) | 0.05 |
| Hold-out: direction of change right | 57% (a coin gets 50%; with this few pairs, under 62% is noise) |

Negative coefficients mean more shadow when stocks are low, which is the right way round.

## Reading it

- The effect is real but faint: averaged over hundreds of tanks, shadows do move with stocks once the sun angle is allowed for, and it survives on years the tank selection never saw.
- It is far too noisy to trade. The estimate misses by several times a normal weekly move, and changes between passes are unrelated to actual changes, so it cannot call this week's EIA number.
- Why: at 10 m a whole roof shadow is one to three pixels, the scene date rarely lines up with EIA's Friday snapshot, and cloud removes over half the passes. Paid 30-50 cm imagery is what funds use, and even that edge has been sold widely since about 2015.
- Oil prices were not tested: without a usable stocks nowcast there is nothing to trade.

Data: Sentinel-2 L2A from the public AWS archive (tile 14SQE), EIA series W_EPC0_SAX_YCUOK_MBBL. Rebuild the shadow file with `python scripts/oil_tanks_fetch.py` (needs rasterio and scipy).
