flowchart LR
  subgraph Dev["Developer / Repo"]
    GITHUB[GitHub Repo]
  end

  subgraph CI["CI/CD – GitHub Actions"]
    BUILD[Build Container Image]\n(Python + your code)
    PUSH[Push to Azure Container Registry]
    RUNJOB[Run Container Apps Job]\n(with sweep args)
    REFRESH[Trigger Power BI Refresh]\n(optional)
  end

  subgraph Azure["Azure Platform"]
    subgraph ACR["Azure Container Registry"]
      IMG[ca-masters image]
    end

    subgraph CAE["Azure Container Apps"]
      JOB[Container Apps Job]\n(scripts.run_thesis_sweep)
    end

    subgraph STG["Azure Storage"]
      BLOB[Blob Storage]\n(thesis_artifacts/<timestamp>/…)
    end

    subgraph APP["Dashboards (Choose one or both)"]
      PBI[Power BI Service]\n(Import CSV from Blob)
      WA[Streamlit Web App]\n(Azure Web App / Container Apps)
    end
  end

  subgraph Users["Consumers"]
    ANALYST[You / Committee / Stakeholders]
  end

  GITHUB --> BUILD --> PUSH --> IMG
  IMG --> RUNJOB --> JOB
  JOB -->|writes CSV/PNG| BLOB

  BLOB -->|dataset source| PBI
  PBI -->|published report| ANALYST

  BLOB -->|HTTP (SAS URL)| WA
  WA -->|web UI| ANALYST

  RUNJOB -.optional.-> REFRESH -.API call.-> PBI
