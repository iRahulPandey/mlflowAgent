#!/usr/bin/env python3
"""
MLflow MCP Server

This script creates a streamlined Model Context Protocol (MCP) server 
that connects to a local MLflow tracking server, exposing core MLflow functionality
through standardized tools that AI assistants can use.

Environment variables:
    MLFLOW_TRACKING_URI: URI of the MLflow tracking server (default: http://localhost:8080)
    LOG_LEVEL: Logging level (default: INFO)

Usage:
    python optimized_mlflow_server.py
"""

import json
import logging
import os
import sys
from typing import Dict, Any, Optional
from datetime import datetime

import mlflow
from mlflow import MlflowClient

# Set up logging
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("mlflow-mcp-server")

# Set MLflow tracking URI from environment variable or use default
TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:8080")
mlflow.set_tracking_uri(uri=TRACKING_URI)
logger.info(f"Using MLflow tracking server at: {TRACKING_URI}")

# Get MLflow client
client = MlflowClient()

try:
    from mcp.server.fastmcp import FastMCP
    
    # Initialize FastMCP server with focused instructions
    mcp = FastMCP(
        name="mlflow",
        instructions="""
        I can help you interact with your MLflow tracking server to manage machine learning 
        experiments and models.
        
        You can ask me to:
        - List registered models and experiments
        - Get detailed information about specific models
        - Show system information about your MLflow server
        """
    )
except ImportError:
    logger.error("Failed to import MCP. Please install with: pip install mcp[cli]")
    sys.exit(1)


class MLflowTools:
    """Collection of helper utilities for MLflow interactions."""
    
    @staticmethod
    def _format_timestamp(timestamp_ms: int) -> str:
        """Convert a millisecond timestamp to a human-readable string."""
        if not timestamp_ms:
            return "N/A"
        dt = datetime.fromtimestamp(timestamp_ms / 1000.0)
        return dt.strftime("%Y-%m-%d %H:%M:%S")


@mcp.tool()
def list_models(name_contains: str = "", max_results: int = 100) -> str:
    """
    List all registered models in the MLflow model registry, with optional filtering.
    
    Args:
        name_contains: Optional filter to only include models whose names contain this string
        max_results: Maximum number of results to return (default: 100)
    
    Returns:
        A JSON string containing all registered models matching the criteria.
    """
    logger.info(f"Fetching registered models (filter: '{name_contains}', max: {max_results})")
    
    try:
        # Get all registered models
        registered_models = client.search_registered_models(max_results=max_results)
        
        # Filter by name if specified
        if name_contains:
            registered_models = [
                model for model in registered_models 
                if name_contains.lower() in model.name.lower()
            ]
        
        # Create a list to hold model information
        models_info = []
        
        # Extract relevant information for each model
        for model in registered_models:
            model_info = {
                "name": model.name,
                "creation_timestamp": MLflowTools._format_timestamp(model.creation_timestamp),
                "last_updated_timestamp": MLflowTools._format_timestamp(model.last_updated_timestamp),
                "description": model.description or "",
                "tags": {tag.key: tag.value for tag in model.tags} if hasattr(model, "tags") else {},
                "latest_versions": []
            }
            
            # Add the latest versions if available
            if model.latest_versions and len(model.latest_versions) > 0:
                for version in model.latest_versions:
                    version_info = {
                        "version": version.version,
                        "status": version.status,
                        "stage": version.current_stage,
                        "creation_timestamp": MLflowTools._format_timestamp(version.creation_timestamp),
                        "run_id": version.run_id
                    }
                    model_info["latest_versions"].append(version_info)
            
            models_info.append(model_info)
        
        result = {
            "total_models": len(models_info),
            "models": models_info
        }
        
        return json.dumps(result, indent=2)
    
    except Exception as e:
        error_msg = f"Error listing models: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return json.dumps({"error": error_msg})


@mcp.tool()
def list_experiments(name_contains: str = "", max_results: int = 100) -> str:
    """
    List all experiments in the MLflow tracking server, with optional filtering.
    
    Args:
        name_contains: Optional filter to only include experiments whose names contain this string
        max_results: Maximum number of results to return (default: 100)
    
    Returns:
        A JSON string containing all experiments matching the criteria.
    """
    logger.info(f"Fetching experiments (filter: '{name_contains}', max: {max_results})")
    
    try:
        # Get all experiments
        experiments = client.search_experiments()
        
        # Filter by name if specified
        if name_contains:
            experiments = [
                exp for exp in experiments 
                if name_contains.lower() in exp.name.lower()
            ]
        
        # Limit to max_results
        experiments = experiments[:max_results]
        
        # Create a list to hold experiment information
        experiments_info = []
        
        # Extract relevant information for each experiment
        for exp in experiments:
            exp_info = {
                "experiment_id": exp.experiment_id,
                "name": exp.name,
                "artifact_location": exp.artifact_location,
                "lifecycle_stage": exp.lifecycle_stage,
                "creation_time": MLflowTools._format_timestamp(exp.creation_time) if hasattr(exp, "creation_time") else None,
                "tags": {tag.key: tag.value for tag in exp.tags} if hasattr(exp, "tags") else {}
            }
            
            # Get the run count for this experiment
            try:
                runs = client.search_runs(experiment_ids=[exp.experiment_id], max_results=1)
                if runs:
                    # Just get the count of runs, not the actual runs
                    run_count = client.search_runs(experiment_ids=[exp.experiment_id], max_results=1000)
                    exp_info["run_count"] = len(run_count)
                else:
                    exp_info["run_count"] = 0
            except Exception as e:
                logger.warning(f"Error getting run count for experiment {exp.experiment_id}: {str(e)}")
                exp_info["run_count"] = "Error getting count"
            
            experiments_info.append(exp_info)
        
        result = {
            "total_experiments": len(experiments_info),
            "experiments": experiments_info
        }
        
        return json.dumps(result, indent=2)
    
    except Exception as e:
        error_msg = f"Error listing experiments: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return json.dumps({"error": error_msg})


@mcp.tool()
def get_model_details(model_name: str) -> str:
    """
    Get detailed information about a specific registered model.
    
    Args:
        model_name: The name of the registered model
        
    Returns:
        A JSON string containing detailed information about the model.
    """
    logger.info(f"Fetching details for model: {model_name}")
    
    try:
        # Get the registered model
        model = client.get_registered_model(model_name)
        
        model_info = {
            "name": model.name,
            "creation_timestamp": MLflowTools._format_timestamp(model.creation_timestamp),
            "last_updated_timestamp": MLflowTools._format_timestamp(model.last_updated_timestamp),
            "description": model.description or "",
            "tags": {tag.key: tag.value for tag in model.tags} if hasattr(model, "tags") else {},
            "versions": []
        }
        
        # Get all versions for this model
        versions = client.search_model_versions(f"name='{model_name}'")
        
        for version in versions:
            version_info = {
                "version": version.version,
                "status": version.status,
                "stage": version.current_stage,
                "creation_timestamp": MLflowTools._format_timestamp(version.creation_timestamp),
                "source": version.source,
                "run_id": version.run_id
            }
            
            # Get additional information about the run if available
            if version.run_id:
                try:
                    run = client.get_run(version.run_id)
                    # Extract only essential run information to avoid serialization issues
                    run_metrics = {}
                    for k, v in run.data.metrics.items():
                        try:
                            run_metrics[k] = float(v)
                        except:
                            run_metrics[k] = str(v)
                            
                    version_info["run"] = {
                        "status": run.info.status,
                        "start_time": MLflowTools._format_timestamp(run.info.start_time),
                        "end_time": MLflowTools._format_timestamp(run.info.end_time) if run.info.end_time else None,
                        "metrics": run_metrics
                    }
                except Exception as e:
                    logger.warning(f"Error getting run details for {version.run_id}: {str(e)}")
                    version_info["run"] = "Error retrieving run details"
            
            model_info["versions"].append(version_info)
        
        return json.dumps(model_info, indent=2)
    
    except Exception as e:
        error_msg = f"Error getting model details: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return json.dumps({"error": error_msg})


@mcp.tool()
def get_system_info() -> str:
    """
    Get information about the MLflow tracking server and system.
    
    Returns:
        A JSON string containing system information.
    """
    logger.info("Getting MLflow system information")
    
    try:
        info = {
            "mlflow_version": mlflow.__version__,
            "tracking_uri": mlflow.get_tracking_uri(),
            "registry_uri": mlflow.get_registry_uri(),
            "artifact_uri": mlflow.get_artifact_uri(),
            "python_version": sys.version,
            "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Get experiment count
        try:
            experiments = client.search_experiments()
            info["experiment_count"] = len(experiments)
        except Exception as e:
            logger.warning(f"Error getting experiment count: {str(e)}")
            info["experiment_count"] = "Error retrieving count"
        
        # Get model count
        try:
            models = client.search_registered_models()
            info["model_count"] = len(models)
        except Exception as e:
            logger.warning(f"Error getting model count: {str(e)}")
            info["model_count"] = "Error retrieving count"
        
        # Get active run count
        try:
            active_runs = 0
            for exp in experiments:
                runs = client.search_runs(
                    experiment_ids=[exp.experiment_id],
                    filter_string="attributes.status = 'RUNNING'",
                    max_results=1000
                )
                active_runs += len(runs)
            
            info["active_runs"] = active_runs
        except Exception as e:
            logger.warning(f"Error getting active run count: {str(e)}")
            info["active_runs"] = "Error retrieving count"
        
        return json.dumps(info, indent=2)
    
    except Exception as e:
        error_msg = f"Error getting system info: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return json.dumps({"error": error_msg})
    
if __name__ == "__main__":
    try:
        logger.info(f"Starting optimized MLflow MCP server with tracking URI: {TRACKING_URI}")
        mcp.run(transport="stdio")
    except Exception as e:
        logger.error(f"Error running MCP server: {str(e)}", exc_info=True)
        sys.exit(1)