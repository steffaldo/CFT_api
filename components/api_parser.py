for _, row in dff.iterrows():


    # =========== Farm section ============

    farm_input = {
        "country": "Poland", 
        "territory": None,
        "climate": "Cool Temperate Moist",
        "average_temperature": {"value": 10, "unit": "°C"},
        "latitude": 52.679,
        "longitude": 20.030,
        "soil_characteristics": "Sandy Soils",
        "farm_identifier": row["farm_id"]
    }

    # =========== General section ============

    general_input = {
        "grazing_area": {
            "value": row["general.grazing_area_ha"],
            "unit": "ha"
        },
        "feed_approach": 1, # 1 = dmi
        "fertilizer_approach": 2, # 2 = Grazing, grass silage and hay area combined
    }

    # =========== Milk production section ============

    milk_production_input = {
        "variety": row["main_breed_variety"],
        "reporting_year": row["milk_year"],
        "date_time": "start",
        "date_month": 1, # Season always starts in Jan
        "name": row["farm_id"] + str("_") + str(row["milk_year"]),
        "product_dry": {"value": row["total_milk_production_litres"], "unit": "litres"},
        "fat_content": row["milk_fat_content_percent"],
        "protein_content": row["milk_protein_content_percent"],
        "protein_measure": 1 # 1 = true protein
    }

    # =========== Herd sections ============

    herd_sections_input = []

    for herd in herd_sections:
        herd_sections_input.append({
            "phase": herd["cft_name"],
            "animals": row[f"{herd['cft_name']}.herd_count"],
            "live_weight": {
                "value": row[f"{herd['cft_name']}.herd_weight_kg"],
                "unit": "kg"
            },
            "sold_animals": row[f"{herd['cft_name']}.sold_count"],
            "sold_weight": {
                "value": row[f"{herd['cft_name']}.sold_weight_kg"],
                "unit": "kg"
            },
            "purchased_animals": row[f"{herd['cft_name']}.purchased_count"],
            "purchased_weight": {
                "value": row[f"{herd['cft_name']}.purchased_weight_kg"],
                "unit": "kg"
            }
        })


    # =========== Grazing section ============

    grazing_input = []

    for herd in herd_sections:
        grazing_input.append({
            "herd_section": herd["cft_name"],
            "days": row[f"{herd['cft_name']}.grazing_days"],
            "hours": row[f"{herd['cft_name']}.grazing_hours_per_day"],
            "category": 2, # 2 = Confined pasture 
            "quality": id_mappings["grazing_quality"][row[f"{herd['cft_name']}.grazing_quality"]] # has to be int  1 =  high, 2 = low
        })



    # =========== Fertilizers section ============

    fertilizers_input = []

    for fertilizer in fertilizers:

        # if custom NPK
        if fertilizer["cft_id"] == 44:
            {
                "type": fertilizer["cft_id"], 
                "production": 8, # 8 = Europe 2014
                "custom_ingredients": {
                    "n_total_percentage": 6, # 6% as defined by Pawel
                    "n_ammonia_percentage": 6, # 6% as defined by Pawel
                    "p2o5_percentage": 20, # 20% as defined by Pawel
                    "p2o5_percentage_type_id": 4, # 4 = P2O5
                    "k2o_percentage": 30, # 30% as defined by Pawel
                    "k2o_percentage_type_id": 5 # 5 = K2O 
                },
                "application_rate": {
                    "value": row[f"fertilizers.{fertilizer['key']}.t_per_ha"],
                    "unit": units["fertilizer_application_rate"]
                },
                "application_date": "unknown",
                "rate_measure": "product",
                "inhibition": fertilizer["inhibition"] 
            },
        else:
            {
                "type": fertilizer["cft_id"], 
                "production": 8, # 8 = Europe 2014
                "application_rate": {
                    "value": row[f"fertilizers.{fertilizer['key']}.t_per_ha"],
                    "unit": units["fertilizer_application_rate"]
                },
                "application_date": "unknown",
                "rate_measure": "product",
                "inhibition": fertilizer["inhibition"]
            }


    # =========== Feed components section ============

    feed_components_input = []

    for feed in feed_items:
        
        for hs in herd_sections:
            feed_components_input.append({
                "item": feed["cft_id"],
                "region": feed["region_name"],
                "herd_section": hs["cft_name"],
                "dry_matter": {
                    "value": row[f"feed.{feed["cft_name"]}.{hs["cft_name"]}.tonne"],
                    "unit": units["feed_weight"]
                },
                "certified": False
            })

    # =========== Manure section ============

    manure_inputs = []

    herd_sections = ["calf_dairy", "heifer", "cow_milk", "cow_dry"]

    for herd in herd_sections:
        manure_type = row[f"manure_type.{herd}"] # names of columns
        
        if manure_type != "PIT STORAGE AND SOLID STORAGE":
            manure_inputs.extend([
                {"herd_section": herd, "type": 6, "allocation": 50},  # Pit Storage
                {"herd_section": herd, "type": 1, "allocation": 50},  # Solid Storage
            ])
        else:
            manure_inputs.append({
                "herd_section": herd,
                "type": manure_type,
                "allocation": 100
            })

    # =========== Compile dairy input ============

    dairy_input = {
        "farm": farm_input,
        "general": general_input,
        "milk_production": milk_production_input,
        "herd_sections": herd_sections_input,
        "grazing": grazing_input,
        "fertilizers": fertilizers_input,
        "feed_components": feed_components_input,
        "feed_additives": [], # leave empty as no additives
        "manure": manure_inputs,
        "direct_energy": [],
        "transport": []
    }

    print(dairy_input)

    # --- Call CFT API with dairy_input here --- #