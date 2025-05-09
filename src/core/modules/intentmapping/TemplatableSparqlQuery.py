from pydantic import BaseModel, Field, create_model
from typing import TypeVar, Generic, Type
from langchain_core.tools import StructuredTool

from lib.abi import logger

from .GenericWorkflow import GenericWorkflow


def templatable_queries():
    from src import services
    
    results = services.triple_store_service.query("""
        PREFIX intentMapping: <http://ontology.naas.ai/intentMapping/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?query ?label ?description ?sparqlTemplate ?hasArgument
        WHERE {
            ?query a intentMapping:TemplatableSparqlQuery ;
                intentMapping:intentDescription ?description ;
                intentMapping:sparqlTemplate ?sparqlTemplate ;
                intentMapping:hasArgument ?hasArgument ;
                rdfs:label ?label .
        }
    """)

    queries = {}
    
    for result in results:
        query, label, description, sparqlTemplate, hasArgument = result
        queries[query] = {
            "label": label,
            "description": description,
            "sparqlTemplate": sparqlTemplate,
            "hasArgument": [hasArgument] if (query not in queries or queries[query].get("hasArgument") is None) else queries[query].get("hasArgument") + [hasArgument]
        }

    arguments = {}
    for templatableQuery in queries:
        
        for argument in queries[templatableQuery].get("hasArgument"):
            q = """
                PREFIX intentMapping: <http://ontology.naas.ai/intentMapping/>
                
                SELECT ?argument ?name ?description ?validationPattern ?validationFormat
                WHERE {
                    BIND(<""" + str(argument) + """> AS ?argument)
                    ?argument a intentMapping:QueryArgument ;
                        intentMapping:argumentName ?name ;
                        intentMapping:argumentDescription ?description ;
                        intentMapping:validationPattern ?validationPattern ;
                        intentMapping:validationFormat ?validationFormat .
                }
            """
            logger.debug(f'Query: {q}')
            results = services.triple_store_service.query(q)
            
            for result in results:
                argument, name, description, validationPattern, validationFormat = result
                
                arguments[argument] = {
                    "name": name,
                    "description": description,
                    "validationPattern": validationPattern,
                    "validationFormat": validationFormat
                }
    return queries, arguments

def load_workflows():
    workflows = []

    queries, arguments = templatable_queries()

    # Now for each query, we need to create a Pydantic BaseModel based on the arguments
    for _query in queries:
        query = queries[_query]

        # Arguments Model with validation patterns
        arguments_model = create_model(
            f"{query['label'].capitalize()}Arguments", 
            **{
                arguments[argument]["name"]: (
                    str, 
                    Field(
                        ...,
                        description=arguments[argument]["description"],
                        pattern=arguments[argument]["validationPattern"],
                        # You could also add additional metadata from validationFormat if needed
                        example=arguments[argument]["validationFormat"]
                    )
                )
                for argument in query.get("hasArgument")
            }
        )

        p = GenericWorkflow[arguments_model](query["label"], query["description"], query["sparqlTemplate"], arguments_model)
        workflows.append(p)

    return workflows
