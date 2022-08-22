from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Union

from graphql import (
    parse,
    visit,
    Visitor,
    OperationDefinitionNode,
    OperationType,
    FragmentDefinitionNode,
    FragmentSpreadNode,
)

from qenerate.core.feature_flag_parser import FeatureFlagParser, FeatureFlags


class GQLDefinitionType(Enum):
    QUERY = 1
    FRAGMENT = 2


@dataclass
class GQLDefinition:
    feature_flags: FeatureFlags
    source_file: Path
    kind: GQLDefinitionType
    definition: str
    name: str
    fragment_dependencies: list[str]


class DefinitionVisitor(Visitor):
    def __init__(self, source_file_path: Path, feature_flags: FeatureFlags):
        Visitor.__init__(self)
        self.definitions: list[GQLDefinition] = []
        self._feature_flags = feature_flags
        self._source_file_path = source_file_path
        self._stack: list[GQLDefinition] = []

    def _node_name(
        self,
        node: Union[
            OperationDefinitionNode, FragmentDefinitionNode, FragmentSpreadNode
        ],
    ) -> str:
        if not node.name:
            # TODO: proper error
            raise ValueError(f"{node} does not have a name")
        return node.name.value

    def _node_body(
        self,
        node: Union[OperationDefinitionNode, FragmentDefinitionNode],
    ) -> str:
        if not node.loc:
            # TODO: proper error
            raise ValueError(f"{node} does not have loc set")
        start = node.loc.start_token.start
        end = node.loc.end_token.end
        body = node.loc.source.body[start:end]
        return body

    def _add_definition(self):
        if self._stack:
            self.definitions.append(self._stack.pop())

    def enter_operation_definition(self, node: OperationDefinitionNode, *_):
        body = self._node_body(node)
        name = self._node_name(node)

        if node.operation != OperationType.QUERY:
            # TODO: logger
            # TODO: raise
            print(
                "[WARNING] Skipping operation definition because"
                f" it is not a query: \n{body}"
            )
            return

        definition = GQLDefinition(
            kind=GQLDefinitionType.QUERY,
            definition=body,
            source_file=self._source_file_path,
            feature_flags=self._feature_flags,
            fragment_dependencies=[],
            name=name,
        )
        self._stack.append(definition)

    def leave_operation_definition(self, *_):
        self._add_definition()

    def enter_fragment_spread(self, node: FragmentSpreadNode, *_):
        self._stack[-1].fragment_dependencies.append(self._node_name(node))

    def enter_fragment_definition(self, node: FragmentDefinitionNode, *_):
        body = self._node_body(node)
        name = self._node_name(node)

        definition = GQLDefinition(
            kind=GQLDefinitionType.FRAGMENT,
            definition=body,
            source_file=self._source_file_path,
            feature_flags=self._feature_flags,
            fragment_dependencies=[],
            name=name,
        )
        self._stack.append(definition)

    def leave_fragment_definition(self, *_):
        self._add_definition()


class Preprocessor:
    def process_file(self, file_path: Path) -> list[GQLDefinition]:
        with open(file_path, "r") as f:
            content = f.read()
        feature_flags = FeatureFlagParser.parse(
            query=content,
        )
        document_ast = parse(content)
        visitor = DefinitionVisitor(
            feature_flags=feature_flags,
            source_file_path=file_path,
        )
        visit(document_ast, visitor)
        return visitor.definitions