"""atlas.global_market — US-platform bounded context (S&P 500 stocks + US-listed ETFs).

Pure loads → scorers → writers over the ``atlas_global`` schema; ``providers/`` is the ONLY
off-box boundary. May import the shared kernel (atlas.primitives / atlas.db / atlas.config)
plus four subtree edges — atlas.lenses.compute, atlas.compute.signal_eval,
atlas.compute._session, atlas.portfolio.engine — never atlas.lenses.data or .pipeline.
"""
