from scripts.report_operating_tradeoff import stability_details, summarize


def test_lighter_payload_pass_is_not_a_pass_for_the_original_mission():
    def row(payload, passed):
        return dict(
            status="completed",
            condition=dict(seed="a", temperature_c=20, pressure_kpa=400, payload_g=payload),
            phase="initial",
            screening_pass=passed,
            checks=dict(altitude=passed, static_margin=True),
            metrics=dict(
                apogee_m=31 if passed else 28,
                peak_gauge_kpa=414,
                static_margin_cal=1.2,
                time_step_difference_m=0.001,
            ),
        )

    report = dict(
        baseline_requirement=dict(payload_mass_kg=0.06),
        study=dict(seeds=["a"], temperatures_c=[20], payloads_g=[30, 60], pressures_kpa=[400]),
        results=[row(30, True), row(60, False), dict(status="failed")],
    )
    summary = summarize(report)
    assert summary["completed"] == 2 and summary["failed"] == 1
    assert summary["screening_passes"] == 1 and summary["original_mission_screening_passes"] == 0
    assert summary["by_seed"]["a"]["mission_max_height_m"] == 28
    assert summary["failed_checks"] == dict(altitude=1)


def test_interactions_are_difference_of_measured_differences():
    rows = []
    # Explicit response with a pressure x payload interaction.
    for t in (5, 20, 35):
        for m in (30, 60, 90):
            for p in (200, 300, 400):
                rows.append(
                    dict(
                        status="completed",
                        phase="initial",
                        screening_pass=False,
                        condition=dict(seed="a", temperature_c=t, payload_g=m, pressure_kpa=p),
                        checks=dict(altitude=False),
                        metrics=dict(
                            apogee_m=p * 0.1 - m * 0.01 - p * m * 0.0001,
                            peak_gauge_kpa=p + 10,
                            static_margin_cal=0.5,
                            time_step_difference_m=0.001,
                        ),
                    )
                )
    r = dict(
        results=rows,
        baseline_requirement=dict(payload_mass_kg=0.06),
        study=dict(
            seeds=["a"],
            temperatures_c=[5, 20, 35],
            payloads_g=[30, 60, 90],
            pressures_kpa=[200, 300, 400],
        ),
    )
    effects = summarize(r)["finite_grid_effects"]["a"]
    assert abs(effects["pressure_payload_interaction_m"] - (-1.2)) < 1e-10
    assert effects["pressure_temperature_interaction_m"] == 0


def test_free_ascent_margin_excludes_rail_and_descent_without_replacing_initial_gate():
    flight = dict(
        trace=dict(time_s=[0, 0.1, 0.2, 1, 2, 3], cg_m=[0.31, 0.29, 0.18, 0.16, 0.17, 0.35]),
        rail_exit_s=0.2,
        apogee_s=2,
    )
    assembly = dict(cp_mm=300, dimensions_mm=dict(body_diameter=100))
    details, trace = stability_details(flight, assembly)
    assert abs(details["initial_including_gas_cal"] + 0.1) < 1e-10
    assert abs(details["minimum_free_ascent_including_gas_cal"] - 1.2) < 1e-10
    assert not details["existing_initial_check_changed"]
    assert trace["time_s"][-1] == 2
    flight["rail_exit_s"] = None
    assert stability_details(flight, assembly)[0]["minimum_free_ascent_including_gas_cal"] is None
