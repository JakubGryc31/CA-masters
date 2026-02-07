flowchart LR
  subgraph Dev["Developer"]
    LOCAL[Local dev + git push]
    CLI[az CLI / manual build]
  end

  subgraph Azure["Azure Platform"]
    subgraph ACR["Azure Container Registry"]
      IMG[ca-masters image]
    end

    subgraph CAE["Azure Container Apps"]
      JOB[Container Apps Job]
    end

    subgraph Pipeline["Job execution pipeline"]
      direction TB
      SWEEP[run_thesis_sweep.py<br/>900 episodes]
      QC[qc_after_sweep.py<br/>validate min seeds]
      UPLOAD[upload artifacts<br/>to Blob Storage]
      SWEEP --> QC --> UPLOAD
    end

    subgraph STG["Azure Blob Storage"]
      TS["&lt;timestamp&gt;/<br/>metrics_summary_raw.csv<br/>metrics_summary_grouped.csv<br/>timeseries_samples/"]
      LATEST[latest.txt]
    end

    subgraph DASH["Dashboard"]
      ST[Streamlit Web App<br/>streamlit_app.py]
    end
  end

  subgraph Users["Consumers"]
    ANALYST[You / Committee]
  end

  CLI -->|docker build + push| IMG
  IMG --> JOB
  JOB --> Pipeline
  UPLOAD -->|writes CSV files| TS
  UPLOAD -->|updates pointer| LATEST

  LATEST -->|resolves run folder| ST
  TS -->|HTTP / SAS or MI| ST
  ST -->|interactive charts| ANALYST

  LOCAL -->|git push| CLI