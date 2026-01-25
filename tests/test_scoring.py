"""
Tests for the scoring engine and index calculations.
"""


class TestSCICalculation:
    """Tests for Space Creation Index calculation."""

    def test_sci_nba_high_scorer(self, nba_starter_stats):
        """High scorer should have high SCI."""
        from core.scoring import calculate_sci

        sci = calculate_sci(nba_starter_stats)

        # 26.3 PPG, 28.5 usage, 8.2 assists = should be high
        assert sci >= 60
        assert sci <= 100

    def test_sci_nba_bench_player(self, nba_bench_stats):
        """Bench player with lower volume should have lower SCI."""
        from core.scoring import calculate_sci

        sci = calculate_sci(nba_bench_stats)

        # 12.8 PPG, 18.5 usage, 2.1 assists = lower
        assert sci < 50
        assert sci >= 0

    def test_sci_nba_efficiency_boost(self):
        """Good shooting efficiency should boost SCI."""
        from core.scoring import PlayerStats, calculate_sci

        efficient_shooter = PlayerStats(
            player_id="1",
            name="Efficient",
            team="TEST",
            position="SG",
            sport="nba",
            points_per_game=15.0,
            usage_rate=20.0,
            assists_per_game=3.0,
            field_goal_pct=0.55,  # Very efficient
            three_point_pct=0.42,  # Elite 3PT
        )

        inefficient_shooter = PlayerStats(
            player_id="2",
            name="Inefficient",
            team="TEST",
            position="SG",
            sport="nba",
            points_per_game=15.0,
            usage_rate=20.0,
            assists_per_game=3.0,
            field_goal_pct=0.38,  # Poor
            three_point_pct=0.28,  # Below average
        )

        efficient_sci = calculate_sci(efficient_shooter)
        inefficient_sci = calculate_sci(inefficient_shooter)

        assert efficient_sci > inefficient_sci

    def test_sci_nfl_wr(self, nfl_wr_stats):
        """NFL WR should calculate SCI based on targets/receptions."""
        from core.scoring import calculate_sci

        sci = calculate_sci(nfl_wr_stats)

        # 8.5 targets, 5.8 receptions, 78.4 yards
        assert sci >= 40
        assert sci <= 100

    def test_sci_nfl_rb(self, nfl_rb_stats):
        """NFL RB should factor in receiving work."""
        from core.scoring import calculate_sci

        sci = calculate_sci(nfl_rb_stats)

        assert sci >= 30
        assert sci <= 100


class TestRMICalculation:
    """Tests for Role Motion Index calculation."""

    def test_rmi_starter_lower(self, nba_starter_stats):
        """Starters should have lower RMI (more stable)."""
        from core.scoring import calculate_rmi

        rmi = calculate_rmi(nba_starter_stats)

        # Starter with high games_started_pct should be stable
        assert rmi < 50

    def test_rmi_bench_higher(self, nba_bench_stats):
        """Bench players should have higher RMI (scheme dependent)."""
        from core.scoring import calculate_rmi

        rmi = calculate_rmi(nba_bench_stats)

        # Non-starter with low games_started_pct
        assert rmi > 50

    def test_rmi_high_minutes_variance(self):
        """High minutes variance should increase RMI."""
        from core.scoring import PlayerStats, calculate_rmi

        stable = PlayerStats(
            player_id="1",
            name="Stable",
            team="TEST",
            position="PG",
            sport="nba",
            is_starter=True,
            games_started_pct=1.0,
            minutes_trend=1.0,  # Low variance
            usage_trend=0.5,
        )

        volatile = PlayerStats(
            player_id="2",
            name="Volatile",
            team="TEST",
            position="PG",
            sport="nba",
            is_starter=True,
            games_started_pct=1.0,
            minutes_trend=8.0,  # High variance
            usage_trend=5.0,
        )

        stable_rmi = calculate_rmi(stable)
        volatile_rmi = calculate_rmi(volatile)

        assert volatile_rmi > stable_rmi


class TestGISCalculation:
    """Tests for Gravity Impact Score calculation."""

    def test_gis_high_usage(self, nba_starter_stats):
        """High usage player should have high GIS."""
        from core.scoring import calculate_gis

        gis = calculate_gis(nba_starter_stats)

        # 28.5 usage, 8.2 assists, good 3PT = high gravity
        assert gis >= 60

    def test_gis_three_point_shooter(self):
        """Elite 3PT shooter should have high GIS."""
        from core.scoring import PlayerStats, calculate_gis

        sniper = PlayerStats(
            player_id="1",
            name="Sniper",
            team="TEST",
            position="SG",
            sport="nba",
            usage_rate=15.0,
            assists_per_game=2.0,
            points_per_game=12.0,
            three_point_pct=0.45,  # Elite
        )

        non_shooter = PlayerStats(
            player_id="2",
            name="Non-Shooter",
            team="TEST",
            position="SG",
            sport="nba",
            usage_rate=15.0,
            assists_per_game=2.0,
            points_per_game=12.0,
            three_point_pct=0.28,  # Below average
        )

        sniper_gis = calculate_gis(sniper)
        non_shooter_gis = calculate_gis(non_shooter)

        assert sniper_gis > non_shooter_gis


class TestODCalculation:
    """Tests for Opportunity Delta calculation."""

    def test_od_positive_trend(self, nba_starter_stats):
        """Positive trends should result in positive OD."""
        from core.scoring import calculate_od

        # nba_starter_stats has positive trends
        od = calculate_od(nba_starter_stats)

        assert od > 0
        assert od <= 50

    def test_od_negative_trend(self, nba_bench_stats):
        """Negative trends should result in negative OD."""
        from core.scoring import calculate_od

        # nba_bench_stats has negative trends
        od = calculate_od(nba_bench_stats)

        assert od < 0
        assert od >= -50

    def test_od_clamped_range(self):
        """OD should always be between -50 and +50."""
        from core.scoring import PlayerStats, calculate_od

        extreme_up = PlayerStats(
            player_id="1",
            name="Rising",
            team="TEST",
            position="PG",
            sport="nba",
            minutes_trend=30.0,  # Extreme
            usage_trend=20.0,
            points_trend=15.0,
        )

        extreme_down = PlayerStats(
            player_id="2",
            name="Falling",
            team="TEST",
            position="PG",
            sport="nba",
            minutes_trend=-30.0,
            usage_trend=-20.0,
            points_trend=-15.0,
        )

        assert calculate_od(extreme_up) == 50  # Clamped
        assert calculate_od(extreme_down) == -50  # Clamped


class TestMSFCalculation:
    """Tests for Matchup Space Fit calculation."""

    def test_msf_no_matchup_data(self, nba_starter_stats):
        """No matchup data should return neutral 50."""
        from core.scoring import calculate_msf

        msf = calculate_msf(nba_starter_stats)

        assert msf == 50

    def test_msf_good_matchup(self, nba_stats_with_matchup):
        """Good matchup (high def rating, FP allowed) should boost MSF."""
        from core.scoring import calculate_msf

        msf = calculate_msf(nba_stats_with_matchup)

        # 115.5 def rating, 38.5 FP allowed = good matchup
        assert msf > 60

    def test_msf_bad_matchup(self):
        """Bad matchup (low def rating) should lower MSF."""
        from core.scoring import PlayerStats, calculate_msf

        tough_matchup = PlayerStats(
            player_id="1",
            name="Test",
            team="TEST",
            position="PG",
            sport="nba",
            opponent_def_rating=102.0,  # Elite defense
            opponent_pace=95.0,  # Slow pace
            opponent_vs_position=22.0,  # Low FP allowed
        )

        msf = calculate_msf(tough_matchup)

        assert msf < 40


class TestCompositeScore:
    """Tests for composite score calculation."""

    def test_composite_floor_mode(self, nba_starter_stats, nba_bench_stats):
        """Floor mode should favor stable players."""
        from core.scoring import RiskMode, calculate_indices, composite_score

        starter_indices = calculate_indices(nba_starter_stats)
        bench_indices = calculate_indices(nba_bench_stats)

        starter_floor = composite_score(starter_indices, RiskMode.FLOOR)
        bench_floor = composite_score(bench_indices, RiskMode.FLOOR)

        # Starter should score higher in floor mode due to stability
        assert starter_floor > bench_floor

    def test_composite_ceiling_mode(self, nba_starter_stats):
        """Ceiling mode should weight upside metrics."""
        from core.scoring import RiskMode, calculate_indices, composite_score

        indices = calculate_indices(nba_starter_stats)

        floor_score = composite_score(indices, RiskMode.FLOOR)
        ceiling_score = composite_score(indices, RiskMode.CEILING)

        # Different modes should produce different scores
        assert floor_score != ceiling_score

    def test_composite_score_range(self, nba_starter_stats):
        """Composite score should always be 0-100."""
        from core.scoring import RiskMode, calculate_indices, composite_score

        indices = calculate_indices(nba_starter_stats)

        for mode in [RiskMode.FLOOR, RiskMode.MEDIAN, RiskMode.CEILING]:
            score = composite_score(indices, mode)
            assert 0 <= score <= 100


class TestComparePlayers:
    """Tests for player comparison."""

    def test_compare_returns_decision(self, nba_starter_stats, nba_bench_stats):
        """Compare should return a decision dict."""
        from core.scoring import RiskMode, compare_players

        result = compare_players(nba_starter_stats, nba_bench_stats, RiskMode.MEDIAN)

        assert "decision" in result
        assert "confidence" in result
        assert "score_a" in result
        assert "score_b" in result
        assert "margin" in result
        assert "indices_a" in result
        assert "indices_b" in result

    def test_compare_starter_wins(self, nba_starter_stats, nba_bench_stats):
        """Better player should win comparison."""
        from core.scoring import RiskMode, compare_players

        result = compare_players(nba_starter_stats, nba_bench_stats, RiskMode.MEDIAN)

        assert "Test Player A" in result["decision"]
        assert result["score_a"] > result["score_b"]

    def test_compare_confidence_levels(self):
        """Confidence should scale with margin."""
        from core.scoring import PlayerStats, RiskMode, compare_players

        player_a = PlayerStats(
            player_id="1",
            name="Player A",
            team="TEST",
            position="PG",
            sport="nba",
            points_per_game=25.0,
            usage_rate=28.0,
            assists_per_game=8.0,
        )

        player_b = PlayerStats(
            player_id="2",
            name="Player B",
            team="TEST",
            position="PG",
            sport="nba",
            points_per_game=10.0,
            usage_rate=15.0,
            assists_per_game=2.0,
        )

        result = compare_players(player_a, player_b, RiskMode.MEDIAN)

        # Large margin should produce high confidence
        assert result["confidence"] in ["low", "medium", "high"]
        if result["margin"] > 15:
            assert result["confidence"] == "high"

    def test_compare_close_players(self):
        """Very similar players should produce low confidence."""
        from core.scoring import PlayerStats, RiskMode, compare_players

        player_a = PlayerStats(
            player_id="1",
            name="Player A",
            team="TEST",
            position="PG",
            sport="nba",
            points_per_game=18.0,
            usage_rate=22.0,
            assists_per_game=5.0,
        )

        player_b = PlayerStats(
            player_id="2",
            name="Player B",
            team="TEST",
            position="PG",
            sport="nba",
            points_per_game=17.5,
            usage_rate=21.5,
            assists_per_game=4.8,
        )

        result = compare_players(player_a, player_b, RiskMode.MEDIAN)

        assert result["margin"] < 10
        assert result["confidence"] in ["low", "medium"]
