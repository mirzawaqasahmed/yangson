# Copyright © 2016, 2017 CZ.NIC, z. s. p. o.
#
# This file is part of Yangson.
#
# Yangson is free software: you can redistribute it and/or modify it under the
# terms of the GNU Lesser General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# Yangson is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with Yangson.  If not, see <http://www.gnu.org/licenses/>.

"""Classes representing YANG schema nodes.

This module implements the following classes:

* SchemaNode: Abstract class for schema nodes.
* InternalNode: Abstract class for schema nodes that have children.
* GroupNode: Anonymous group of schema nodes.
* DataNode: Abstract class for data nodes.
* TerminalNode: Abstract class for schema nodes that have no children.
* ContainerNode: YANG container node.
* SequenceNode: Abstract class for schema nodes that represent a sequence.
* ListNode: YANG list node.
* ChoiceNode: YANG choice node.
* CaseNode: YANG case node.
* RpcActionNode: YANG rpc or action node.
* InputNode: YANG input node.
* OutputNode: YANG output node.
* NotificationNode: YANG notification node.
* LeafNode: YANG leaf node.
* LeafListNode: YANG leaf-list node.
* AnyContentNode: Abstract superclass for anydata and anyxml nodes..
* AnydataNode: YANG anydata node.
* AnyxmlNode: YANG anyxml node.

This module defines the following exceptions:

* SchemaNodeException: Abstract exception class for schema node errors.
* NonexistentSchemaNode: A schema node doesn't exist.
* BadSchemaNodType: A schema node is of a wrong type.
* BadLeafrefPath: A leafref path is incorrect.
* RawDataError: Abstract exception class for errors in raw data.
* RawMemberError: Object member in raw data doesn't exist in the schema.
* RawTypeError: Raw data value is of incorrect type.
* ValidationError: Abstract exception class for instance validation errors.
* SchemaError: An instance violates a schema constraint.
* SemanticError: An instance violates a semantic rule.
"""

from typing import Any, Dict, List, MutableSet, Optional, Set, Tuple, Union
from .exceptions import YangsonException
from .schemadata import SchemaData, SchemaContext
from .datatype import (DataType, EmptyType, LeafrefType, LinkType,
                       RawScalar, IdentityrefType, YangTypeError)
from .enumerations import Axis, ContentType, DefaultDeny, ValidationScope
from .instvalue import (ArrayValue, EntryValue, ObjectValue, StructuredValue,
                            Value)
from .schpattern import *
from .statement import Statement, WrongArgument
from .typealiases import *
from .xpathparser import XPathParser

class SchemaNode:
    """Abstract class for all schema nodes."""

    def __init__(self):
        """Initialize the class instance."""
        self.name = None # type: Optional[YangIdentifier]
        """Name of the receiver."""
        self.ns = None # type: Optional[YangIdentifier]
        """Namespace of the receiver."""
        self.parent = None # type: Optional["InternalNode"]
        """Parent schema node."""
        self.description = None # type: Optional[str]
        """Description of the receiver."""
        self.must = [] # type: List[Tuple["Expr", Optional[str]]]
        """List of "must" expressions attached to the receiver."""
        self.when = None # type: Optional["Expr"]
        """Optional "when" expression that makes the receiver conditional."""
        self._ctype = None
        """Content type of the receiver."""

    @property
    def qual_name(self) -> QualName:
        """Qualified name of the receiver."""
        return (self.name, self.ns)

    @property
    def config(self) -> bool:
        """Does the receiver (also) represent configuration?"""
        return self.content_type().value & ContentType.config.value != 0

    @property
    def mandatory(self) -> bool:
        """Is the receiver a mandatory node?"""
        return False

    def schema_root(self) -> "GroupNode":
        """Return the root node of the schema."""
        sn = self
        while sn.parent:
            sn = sn.parent
        return sn

    def content_type(self) -> ContentType:
        """Return receiver's content type."""
        return self._ctype if self._ctype else self.parent.content_type()

    def data_parent(self) -> Optional["InternalNode"]:
        """Return the closest ancestor data node."""
        parent = self.parent
        while parent:
            if isinstance(parent, DataNode):
                return parent
            parent = parent.parent

    def iname(self) -> InstanceName:
        """Return the instance name corresponding to the receiver."""
        dp = self.data_parent()
        return (self.name if dp and self.ns == dp.ns
                else self.ns + ":" + self.name)

    def data_path(self) -> DataPath:
        """Return the receiver's data path."""
        dp = self.data_parent()
        return (dp.data_path() if dp else "") + "/" + self.iname()

    def state_roots(self) -> List[DataPath]:
        """Return a list of data paths to descendant state data roots."""
        return [r.data_path() for r in self._state_roots()]

    def from_raw(self, rval: RawValue, jptr: JSONPointer = "") -> Value:
        """Return instance value transformed from a raw value using receiver.

        Args:
            rval: Raw value.
            jptr: JSON pointer of the current instance node.

        Raises:
            RawMemberError: If a member inside `rval` is not defined in the
                schema.
            RawTypeError: If a scalar value inside `rval` is of incorrect type.
        """
        raise NotImplementedError

    def _client_digest(self) -> Dict[str, Any]:
        """Return dictionary of receiver's properties suitable for clients."""
        res = { "kind": self._yang_class() }
        if self.description:
            res["description"] = self.description
        return res

    def _validate(self, inst: "InstanceNode", scope: ValidationScope,
                      ctype: ContentType) -> None:
        """Validate instance against the receiver.

        Args:
            inst: Instance node to be validated.
            scope: Scope of the validation (syntax, semantics or all)
            ctype: Content type of the instance.

        Returns:
            ``None`` if validation succeeds.

        Raises:
            SchemaError: if `inst` violates the schema.
            SemanticError: If a "must" expression evaluates to ``False``.
        """
        pass

    def _iname2qname(self, iname: InstanceName) -> QualName:
        """Translate instance name to qualified name in the receiver's context.
        """
        p, s, loc = iname.partition(":")
        return (loc, p) if s else (p, self.ns)

    def _flatten(self) -> List["SchemaNode"]:
        return [self]

    def _handle_substatements(self, stmt: Statement, sctx: SchemaContext) -> None:
        """Dispatch actions for substatements of `stmt`."""
        for s in stmt.substatements:
            if s.prefix:
                key = (
                    sctx.schema_data.modules[sctx.text_mid].prefix_map[s.prefix][0]
                    + ":" + s.keyword)
            else:
                key = s.keyword
            mname = SchemaNode._stmt_callback.get(key, "_noop")
            method = getattr(self, mname)
            method(s, sctx)

    def _follow_leafref(
            self, xpath: "Expr", init: "TerminalNode") -> Optional["DataNode"]:
        """Return the data node referred to by a leafref path.

        Args:
            xpath: XPath expression compiled from a leafref path.
            init: initial context node
        """
        if isinstance(xpath, LocationPath):
            lft = self._follow_leafref(xpath.left, init)
            if lft is None: return None
            return lft._follow_leafref(xpath.right, init)
        elif isinstance(xpath, Step):
            if xpath.axis == Axis.parent:
                return self.data_parent()
            elif xpath.axis == Axis.child:
                if isinstance(self, InternalNode) and xpath.qname:
                    qname = (xpath.qname if xpath.qname[1]
                                 else (xpath.qname[0], init.ns))
                    return self.get_data_child(*qname)
        elif isinstance(xpath, Root):
            return self.schema_root()
        return None

    def _noop(self, stmt: Statement, sctx: SchemaContext) -> None:
        pass

    def _config_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        if stmt.argument == "true" and self.parent.config:
            self._ctype = ContentType.all
        elif stmt.argument == "false":
            self._ctype = ContentType.nonconfig

    def _description_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        self.description = stmt.argument

    def _must_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        xpp = XPathParser(stmt.argument, sctx)
        mex = xpp.parse()
        if not xpp.at_end():
            raise WrongArgument(stmt)
        ems = stmt.find1("error-message")
        self.must.append((mex, ems.argument if ems else None))

    def _when_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        xpp = XPathParser(stmt.argument, sctx)
        wex = xpp.parse()
        if not xpp.at_end():
            raise WrongArgument(stmt)
        self.when = wex

    def _mandatory_stmt(self, stmt, sctx: SchemaContext) -> None:
        if stmt.argument == "true":
            self._mandatory = True
        elif stmt.argument == "false":
            self._mandatory = False

    def _post_process(self) -> None:
        pass

    def _is_identityref(self) -> bool:
        return False

    def _default_nodes(self, inst: "InstanceNode") -> List["InstanceNode"]:
        return []

    def _tree_line(self) -> str:
        """Return the receiver's contribution to tree diagram."""
        return self._tree_line_prefix() + " " + self.iname()

    def _tree_line_prefix(self) -> str:
        return "+--"

    _stmt_callback = {
        "action": "_rpc_action_stmt",
        "anydata": "_anydata_stmt",
        "anyxml": "_anydata_stmt",
        "case": "_case_stmt",
        "choice": "_choice_stmt",
        "config": "_config_stmt",
        "container": "_container_stmt",
        "default": "_default_stmt",
        "description": "_description_stmt",
        "identity": "_identity_stmt",
        "ietf-netconf-acm:default-deny-all": "_nacm_default_deny_stmt",
        "ietf-netconf-acm:default-deny-write": "_nacm_default_deny_stmt",
        "input": "_input_stmt",
        "key": "_key_stmt",
        "leaf": "_leaf_stmt",
        "leaf-list": "_leaf_list_stmt",
        "list": "_list_stmt",
        "mandatory": "_mandatory_stmt",
        "max-elements": "_max_elements_stmt",
        "min-elements": "_min_elements_stmt",
        "must": "_must_stmt",
        "notification": "_notification_stmt",
        "output": "_output_stmt",
        "ordered-by": "_ordered_by_stmt",
        "presence": "_presence_stmt",
        "rpc": "_rpc_action_stmt",
        "unique": "_unique_stmt",
        "uses": "_uses_stmt",
        "when": "_when_stmt",
        }
    """Map of statement keywords to callback methods."""


class InternalNode(SchemaNode):
    """Abstract class for schema nodes that have children."""

    def __init__(self):
        """Initialize the class instance."""
        super().__init__()
        self.children = [] # type: List[SchemaNode]
        self._mandatory_children = set() # type: MutableSet[SchemaNode]

    @property
    def mandatory(self) -> bool:
        """Is the receiver a mandatory node?"""
        return len(self._mandatory_children) > 0

    def get_child(self, name: YangIdentifier,
                  ns: YangIdentifier = None) -> Optional[SchemaNode]:
        """Return receiver's schema child.

        Args:
            name: Child's name.
            ns: Child's namespace (= `self.ns` if absent).
        """
        ns = ns if ns else self.ns
        todo = []
        for child in self.children:
            if child.name is None:
                todo.append(child)
            elif child.name == name and child.ns == ns:
                return child
        for c in todo:
            return c.get_child(name, ns)

    def get_schema_descendant(
            self, route: SchemaRoute) -> Optional[SchemaNode]:
        """Return descendant schema node or ``None`` if not found.

        Args:
            route: Schema route to the descendant node
                   (relative to the receiver).
        """
        node = self
        for p in route:
            node = node.get_child(*p)
            if node is None: return None
        return node

    def get_data_child(self, name: YangIdentifier,
                       ns: YangIdentifier = None) -> Optional["DataNode"]:
        """Return data node directly under the receiver."""
        ns = ns if ns else self.ns
        todo = []
        for child in self.children:
            if child.name == name and child.ns == ns:
                if isinstance(child, DataNode): return child
                todo.insert(0, child)
            elif not isinstance(child, DataNode):
                todo.append(child)
        for c in todo:
            res = c.get_data_child(name, ns)
            if res: return res

    def filter_children(self, ctype: ContentType = None) -> List[SchemaNode]:
        """Return receiver's children based on content type.

        Args:
            ctype: Content type.
        """
        if ctype is None:
            ctype = self.content_type()
        return [c for c in self.children if
                not isinstance(c, (RpcActionNode, NotificationNode)) and
                c.content_type().value & ctype.value != 0]

    def data_children(self) -> List["DataNode"]:
        """Return the set of all data nodes directly under the receiver."""
        res = []
        for child in self.children:
            if isinstance(child, DataNode):
                res.append(child)
            else:
                res.extend(child.data_children())
        return res

    def from_raw(self, rval: RawObject, jptr: JSONPointer = "") -> ObjectValue:
        """Override the superclass method."""
        if not isinstance(rval, dict):
            raise RawTypeError(jptr, "expected object")
        res = ObjectValue()
        for qn in rval:
            cn = self._iname2qname(qn)
            ch = self.get_data_child(*cn)
            npath = jptr + "/" + qn
            if ch is None:
                raise RawMemberError(npath)
            res[ch.iname()] = ch.from_raw(rval[qn], npath)
        return res

    def _client_digest(self) -> Dict[str, Any]:
        res = super()._client_digest()
        res["children"] = {
            c.iname(): c._client_digest() for c in self.data_children() }
        return res

    def _validate(self, inst: "InstanceNode", scope: ValidationScope,
                      ctype: ContentType) -> None:
        """Extend the superclass method."""
        if scope.value & ValidationScope.syntax.value:   # schema
            self._check_schema_pattern(inst, ctype)
        for m in inst.value:              # all members
            inst._member(m).validate(scope, ctype)

    def _add_child(self, node: SchemaNode) -> None:
        node.parent = self
        self.children.append(node)

    def _child_inst_names(self) -> Set[InstanceName]:
        """Return the set of instance names under the receiver."""
        return frozenset([c.iname() for c in self.data_children()])

    def _check_schema_pattern(self, inst: "InstanceNode",
                             ctype: ContentType) -> None:
        p = self.schema_pattern
        p._eval_when(inst)
        for m in inst.value:
            p = p.deriv(m, ctype)
            if isinstance(p, NotAllowed):
                raise SchemaError(inst, "not allowed: member {}{}".format(
                    m, ("" if ctype == ContentType.all else
                        " (" + ctype.name + ")")))
        if not p.nullable(ctype):
            raise SchemaError(inst, "missing: " + str(p))

    def _make_schema_patterns(self) -> None:
        """Build schema pattern for the receiver and its data descendants."""
        self.schema_pattern = self._schema_pattern()
        for dc in self.data_children():
            if isinstance(dc, InternalNode):
                dc._make_schema_patterns()

    def _schema_pattern(self) -> SchemaPattern:
        todo = [c for c in self.children
                if not isinstance(c, (RpcActionNode, NotificationNode))]
        if not todo: return Empty()
        prev = todo[0]._pattern_entry()
        for c in todo[1:]:
            prev = Pair(c._pattern_entry(), prev)
        return ConditionalPattern(prev, self.when) if self.when else prev

    def _post_process(self) -> None:
        super()._post_process()
        for c in self.children:
            c._post_process()

    def _add_mandatory_child(self, node: SchemaNode) -> None:
        """Add `node` to the set of mandatory children."""
        self._mandatory_children.add(node)

    def _add_defaults(self, inst: "InstanceNode", ctype: ContentType,
                      lazy: bool = False) -> "InstanceNode":
        for c in self.filter_children(ctype):
            if isinstance(c, DataNode):
                inst = c._default_instance(inst, ctype, lazy)
            elif not isinstance(c, (RpcActionNode, NotificationNode)):
                inst = c._add_defaults(inst, ctype)
        return inst

    def _state_roots(self) -> List[SchemaNode]:
        if self.content_type() == ContentType.nonconfig:
            return [self]
        res = []
        for c in self.data_children():
            res.extend(c._state_roots())
        return res

    def _handle_child(
            self, node: SchemaNode, stmt: Statement, sctx: SchemaContext) -> None:
        """Add child node to the receiver and handle substatements."""
        if not sctx.schema_data.if_features(stmt, sctx.text_mid): return
        node.name = stmt.argument
        node.ns = sctx.default_ns
        self._add_child(node)
        node._handle_substatements(stmt, sctx)

    def _augment_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        """Handle **augment** statement."""
        if not sctx.schema_data.if_features(stmt, sctx.text_mid): return
        path = sctx.schema_data.sni2route(stmt.argument, sctx)
        target = self.get_schema_descendant(path)
        if stmt.find1("when"):
            gr = GroupNode()
            target._add_child(gr)
            target = gr
        target._handle_substatements(stmt, sctx)

    def _refine_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        """Handle **refine** statement."""
        target = self.get_schema_descendant(
            sctx.schema_data.sni2route(stmt.argument, sctx))
        if not sctx.schema_data.if_features(stmt, sctx.text_mid):
            target.parent.children.remove(target)
        else:
            target._handle_substatements(stmt, sctx)

    def _uses_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        """Handle uses statement."""
        if not sctx.schema_data.if_features(stmt, sctx.text_mid): return
        grp, gid = sctx.schema_data.get_definition(stmt, sctx)
        if stmt.find1("when"):
            sn = GroupNode()
            self._add_child(sn)
        else:
            sn = self
        sn._handle_substatements(grp, gid)
        for augst in stmt.find_all("augment"):
            sn._augment_stmt(augst, sctx)
        for refst in stmt.find_all("refine"):
            sn._refine_stmt(refst, sctx)

    def _container_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        """Handle container statement."""
        self._handle_child(ContainerNode(), stmt, sctx)

    def _identity_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        """Handle identity statement."""
        if not sctx.schema_data.if_features(stmt, sctx.text_mid): return
        bstmts = stmt.find_all("base")
        bases = set()
        for bst in bstmts:
            bases.add(
                sctx.schema_data.translate_pname(bst.argument, sctx.text_mid))
        sctx.schema_data.identity_bases[
            (stmt.argument, sctx.schema_data.namespace(sctx.text_mid))] = bases

    def _list_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        """Handle list statement."""
        self._handle_child(ListNode(), stmt, sctx)

    def _choice_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        """Handle choice statement."""
        self._handle_child(ChoiceNode(), stmt, sctx)

    def _case_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        """Handle case statement."""
        self._handle_child(CaseNode(), stmt, sctx)

    def _leaf_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        """Handle leaf statement."""
        node = LeafNode()
        node.type = DataType._resolve_type(
            stmt.find1("type", required=True), sctx)
        self._handle_child(node, stmt, sctx)

    def _leaf_list_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        """Handle leaf-list statement."""
        node = LeafListNode()
        node.type = DataType._resolve_type(
            stmt.find1("type", required=True), sctx)
        self._handle_child(node, stmt, sctx)

    def _rpc_action_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        """Handle rpc or action statement."""
        self._handle_child(RpcActionNode(), stmt, sctx)

    def _notification_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        """Handle notification statement."""
        self._handle_child(NotificationNode(), stmt, sctx)

    def _anydata_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        """Handle anydata statement."""
        self._handle_child(AnydataNode(), stmt, sctx)

    def _ascii_tree(self, indent: str) -> str:
        """Return the receiver's subtree as ASCII art."""
        if not self.children: return ""
        cs = []
        for c in self.children:
            cs.extend(c._flatten())
        cs.sort(key=lambda x: x.qual_name)
        res = ""
        for c in cs[:-1]:
            res += (indent + c._tree_line() + "\n" +
                    c._ascii_tree(indent + "|  "))
        return (res + indent + cs[-1]._tree_line() + "\n" +
                cs[-1]._ascii_tree(indent + "   "))

class GroupNode(InternalNode):
    """Anonymous group of schema nodes."""

    def state_roots(self) -> List[DataPath]:
        """Override superclass method."""
        return []

    def _yang_class(self) -> str:
        return "root"

    def _state_roots(self) -> List[SchemaNode]:
        return []

    def _handle_child(self, node: SchemaNode, stmt: Statement,
                     sctx: SchemaContext) -> None:
        if not isinstance(self.parent, ChoiceNode) or isinstance(node, CaseNode):
            super()._handle_child(node, stmt, sctx)
        else:
            cn = CaseNode()
            cn.name = stmt.argument
            cn.ns = sctx.default_ns
            self._add_child(cn)
            cn._handle_child(node, stmt, sctx)

    def _pattern_entry(self) -> SchemaPattern:
        return super()._schema_pattern()

    def _flatten(self) -> List[SchemaNode]:
        res = []
        for c in self.children:
            res.extend(c._flatten())
        return res

class DataNode(SchemaNode):
    """Abstract superclass for all data nodes."""

    def __init__(self):
        """Initialize the class instance."""
        super().__init__()
        self.default_deny = DefaultDeny.none # type: "DefaultDeny"

    def _yang_class(self) -> str:
        return self.__class__.__name__[:-4].lower()

    def _validate(self, inst: "InstanceNode", scope: ValidationScope,
                      ctype: ContentType) -> None:
        """Extend the superclass method."""
        if scope.value & ValidationScope.semantics.value:
            self._check_must(inst)        # must expressions
        super()._validate(inst, scope, ctype)

    def _default_instance(self, pnode: "InstanceNode", ctype: ContentType,
                          lazy: bool = False) -> "InstanceNode":
        iname = self.iname()
        if iname in pnode.value: return pnode
        nm = pnode.put_member(iname, (None,))
        if not self.when or self.when.evaluate(nm):
            wd = self._default_value(nm, ctype, lazy)
            if wd.value is not None:
                return wd.up()
        return pnode

    def _check_must(self, inst: "InstanceNode") -> None:
        for mex in self.must:
            if not mex[0].evaluate(inst):
                msg = "'must' expression is false" if mex[1] is None else mex[1]
                raise SemanticError(inst, msg)

    def _pattern_entry(self) -> SchemaPattern:
        m = Member(self.iname(), self.content_type(), self.when)
        return m if self.mandatory else SchemaPattern.optional(m)

    def _tree_line_prefix(self) -> str:
        return super()._tree_line_prefix() + (
            "ro" if self.content_type() == ContentType.nonconfig else "rw")

    def _nacm_default_deny_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        """Set NACM default access."""
        if stmt.keyword == "default-deny-all":
            self.default_deny = DefaultDeny.all
        elif stmt.keyword == "default-deny-write":
            self.default_deny = DefaultDeny.write

class TerminalNode(SchemaNode):
    """Abstract superclass for terminal nodes in the schema tree."""

    def __init__(self):
        """Initialize the class instance."""
        super().__init__()
        self.type = None # type: DataType
        self._default = None # type: Optional[Value]

    def content_type(self) -> ContentType:
        """Override superclass method."""
        if self._ctype:
            return self._ctype
        return (ContentType.config if self.parent.config else
                ContentType.nonconfig)

    def from_raw(self, rval: RawScalar, jptr: JSONPointer = "") -> ScalarValue:
        """Override the superclass method."""
        try:
            return self.type.from_raw(rval)
        except YangTypeError as e:
            raise RawTypeError(jptr, str(e))

    def _client_digest(self) -> Dict[str, Any]:
        res = super()._client_digest()
        res["base_type"] = self.type.yang_type()
        if self.type.name:
            res["derived"] = self.type.name
        df = self.default
        if df is not None:
            res["dflt"] = self.type.to_raw(df)
        return res

    def _validate(self, inst: "InstanceNode", scope: ValidationScope,
                      ctype: ContentType) -> None:
        """Extend the superclass method."""
        if (scope.value & ValidationScope.syntax.value and
                not self.type.contains(inst.value)):   # data type
            raise SchemaError(inst, "invalid type: " + repr(inst.value))
        if (isinstance(self.type, LinkType) and        # referential integrity
                scope.value & ValidationScope.semantics.value and
                self.type.require_instance):
            try:
                if not inst._deref():
                    raise SemanticError(inst, "required instance missing")
            except YangsonException:
                raise SemanticError(inst, "required instance missing") from None

    def _default_value(self, inst: "InstanceNode", ctype: ContentType,
                       lazy: bool) -> "InstanceNode":
        inst.value = self.default
        return inst

    def _post_process(self) -> None:
        super()._post_process()
        if isinstance(self.type, LeafrefType):
            ref = self._follow_leafref(self.type.path, self)
            if ref is None:
                raise BadLeafrefPath(self)
            self.type.ref_type = ref.type

    def _is_identityref(self) -> bool:
        return isinstance(self.type, IdentityrefType)

    def _default_nodes(self, inst: "InstanceNode") -> List["InstanceNode"]:
        di = self._default_instance(inst, ContentType.all)
        return [] if di is None else [self]
        return inst.put_member(self.iname(), dflt)._node_set()

    def _ascii_tree(self, indent: str) -> str:
        return ""

    def _state_roots(self) -> List[SchemaNode]:
        return [] if self.content_type() == ContentType.config else [self]

class ContainerNode(DataNode, InternalNode):
    """Container node."""

    def __init__(self):
        """Initialize the class instance."""
        super().__init__()
        self.presence = False # type: bool

    @property
    def mandatory(self) -> bool:
        """Is the receiver a mandatory node?"""
        return not self.presence and super().mandatory

    def _client_digest(self) -> Dict[str, Any]:
        res = super()._client_digest()
        res["presence"] = self.presence
        return res

    def _add_mandatory_child(self, node: SchemaNode):
        if not (self.presence or self.mandatory):
            self.parent._add_mandatory_child(self)
        super()._add_mandatory_child(node)

    def _default_instance(self, pnode: "InstanceNode", ctype: ContentType,
                          lazy: bool = False) -> "InstanceNode":
        if self.presence:
            return pnode
        return super()._default_instance(pnode, ctype, lazy)

    def _default_value(self, inst: "InstanceNode", ctype: ContentType,
                       lazy: bool) -> Optional["InstanceNode"]:
        inst.value = ObjectValue()
        return inst if lazy else self._add_defaults(inst, ctype)

    def _default_nodes(self, inst: "InstanceNode") -> List["InstanceNode"]:
        if self.presence: return []
        res = inst.put_member(self.iname(), ObjectValue())
        if self.when is None or self.when.evaluate(res):
            return [res]
        return []

    def _presence_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        self.presence = True

    def _tree_line(self) -> str:
        """Return the receiver's contribution to tree diagram."""
        return super()._tree_line() + ("!" if self.presence else "")

class SequenceNode(DataNode):
    """Abstract class for data nodes that represent a sequence."""

    def __init__(self):
        """Initialize the class instance."""
        super().__init__()
        self.min_elements = 0 # type: int
        self.max_elements = None # type: Optional[int]
        self.user_ordered = False # type: bool

    @property
    def mandatory(self) -> bool:
        """Is the receiver a mandatory node?"""
        return self.min_elements > 0

    def _validate(self, inst: "InstanceNode", scope: ValidationScope,
                      ctype: ContentType) -> None:
        """Extend the superclass method."""
        if isinstance(inst, ArrayEntry):
            super()._validate(inst, scope, ctype)
        else:
            if scope.value & ValidationScope.semantics.value:
                self._check_list_props(inst)
                self._check_cardinality(inst)
            for e in inst:
                super()._validate(e, scope, ctype)

    def _check_cardinality(self, inst: "InstanceNode") -> None:
        if len(inst.value) < self.min_elements:
            raise SemanticError(inst,
                              "number of entries < min-elements ({})".format(
                                  self.min_elements))
        if (self.max_elements is not None and
            len(inst.value) > self.max_elements):
            raise SemanticError(inst,
                              "number of entries > max-elements ({})".format(
                                  self.max_elements))

    def _post_process(self) -> None:
        super()._post_process()
        if self.min_elements > 0:
            self.parent._add_mandatory_child(self)

    def _min_elements_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        self.min_elements = int(stmt.argument)

    def _max_elements_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        arg = stmt.argument
        if arg == "unbounded":
            self.max_elements = None
        else:
            self.max_elements = int(arg)

    def _ordered_by_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        self.user_ordered = stmt.argument == "user"

    def _tree_line(self) -> str:
        """Extend the superclass method."""
        return super()._tree_line() + "*"

    def from_raw(self, rval: RawList, jptr: JSONPointer = "") -> ArrayValue:
        """Override the superclass method."""
        if not isinstance(rval, list):
            raise RawTypeError(jptr, "expected array")
        res = ArrayValue()
        i = 0
        for en in rval:
            i += 1
            res.append(self.entry_from_raw(en, "{}/{}".format(jptr, i)))
        return res

    def entry_from_raw(self, rval: RawEntry, jptr: JSONPointer = "") -> EntryValue:
        """Transform a raw (leaf-)list entry into the cooked form.

        Args:
            rval: raw entry (scalar or object)
            jptr: JSON pointer of the entry

        Raises:
            NonexistentSchemaNode: If a member inside `rval` is not defined
                in the schema.
            YangTypeError: If a scalar value inside `rval` is of incorrect type.
        """
        return super().from_raw(rval, jptr)

class ListNode(SequenceNode, InternalNode):
    """List node."""

    def __init__(self):
        """Initialize the class instance."""
        super().__init__()
        self.keys = [] # type: List[QualName]
        self._key_members = []
        self.unique = [] # type: List[List[SchemaRoute]]

    def _client_digest(self) -> Dict[str, Any]:
        res = super()._client_digest()
        res["keys"] = self._key_members
        return res

    def _check_list_props(self, inst: "InstanceNode") -> None:
        """Check uniqueness of keys and "unique" properties, if applicable."""
        if self.keys:
            self._check_keys(inst)
        for u in self.unique:
            self._check_unique(u, inst)

    def _check_keys(self, inst: "InstanceNode") -> None:
        ukeys = set()
        for i in range(len(inst.value)):
            en = inst.value[i]
            try:
                kval = tuple([en[k] for k in self._key_members])
            except KeyError as e:
                raise SchemaError(
                    inst._entry(i),
                    "missing list key '{}'".format(e.args[0])) from None
            if kval in ukeys:
                raise SemanticError(inst, "non-unique list key: " + repr(
                    kval[0] if len(kval) < 2 else kval))
            ukeys.add(kval)

    def _check_unique(self, unique: List[SchemaRoute],
                          inst: "InstanceNode") -> None:
        uvals = set()
        for en in inst:
            den = en.add_defaults()
            uval = tuple([den._peek_schema_route(sr) for sr in unique])
            if None not in uval:
                if uval in uvals:
                    raise SemanticError(inst, "unique constraint violated")
                else:
                    uvals.add(uval)

    def _default_instance(self, pnode: "InstanceNode", ctype: ContentType,
                          lazy: bool = False) -> "InstanceNode":
        return pnode

    def _post_process(self) -> None:
        super()._post_process()
        for k in self.keys:
            kn = self.get_data_child(*k)
            self._key_members.append(kn.iname())
            if not kn._mandatory:
                kn._mandatory = True
                self._mandatory_children.add(kn)

    def _key_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        self.keys = []
        for k in stmt.argument.split():
            self.keys.append(sctx.schema_data.translate_node_id(k, sctx))

    def _unique_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        uspec = []
        for sid in stmt.argument.split():
            uspec.append(sctx.schema_data.sni2route(sid, sctx))
        self.unique.append(uspec)

    def _tree_line(self) -> str:
        """Return the receiver's contribution to tree diagram."""
        keys = (" [" + " ".join([ k[0] for k in self.keys ]) + "]"
                if self.keys else "")
        return super()._tree_line() + keys

class ChoiceNode(InternalNode):
    """Choice node."""

    def __init__(self):
        """Initialize the class instance."""
        super().__init__()
        self.default_case = None # type: QualName
        self._mandatory = False # type: bool

    @property
    def mandatory(self) -> bool:
        """Is the receiver a mandatory node?"""
        return self._mandatory

    def _add_defaults(self, inst: "InstanceNode",
                      ctype: ContentType) -> "InstanceNode":
        if self.when and not self.when.evaluate(inst):
            return inst
        ac = self._active_case(inst.value)
        if ac:
            return ac._add_defaults(inst, ctype)
        elif self.default_case:
            n = dc = self.get_child(*self.default_case)
            while n is not self:
                if n.when and not n.when.evaluate(inst):
                    return inst
                n = n.parent
            return dc._add_defaults(inst, ctype)
        else:
            return inst

    def _active_case(self, value: ObjectValue) -> Optional["CaseNode"]:
        """Return receiver's case that's active in an instance node value."""
        for c in self.children:
            for cc in c.data_children():
                if cc.iname() in value:
                    return c

    def _pattern_entry(self) -> SchemaPattern:
        if not self.children:
            return Empty()
        prev = self.children[0]._schema_pattern()
        for c in self.children[1:]:
            prev = ChoicePattern(c._schema_pattern(), prev, self.name)
        prev.ctype = self.content_type()
        if not self.mandatory:
            prev = SchemaPattern.optional(prev)
        return ConditionalPattern(prev, self.when) if self.when else prev

    def _post_process(self) -> None:
        super()._post_process()
        if self._mandatory:
            self.parent._add_mandatory_child(self)

    def _config_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        if stmt.argument == "false":
            self._ctype = ContentType.nonconfig

    def _default_nodes(self, inst: "InstanceNode") -> List["InstanceNode"]:
        res = []
        if self.default_case is None: return res
        for cn in self.get_child(*self.default_case).children:
            res.extend(cn._default_nodes(inst))
        return res

    def _tree_line_prefix(self) -> str:
        return super()._tree_line_prefix() + (
            "ro" if self.content_type() == ContentType.nonconfig else "rw")

    def _handle_child(self, node: SchemaNode, stmt: Statement,
                     sctx: SchemaContext) -> None:
        if isinstance(node, CaseNode):
            super()._handle_child(node, stmt, sctx)
        else:
            cn = CaseNode()
            cn.name = stmt.argument
            cn.ns = sctx.default_ns
            self._add_child(cn)
            cn._handle_child(node, stmt, sctx)

    def _default_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        self.default_case = sctx.schema_data.translate_node_id(
            stmt.argument, sctx)

    def _tree_line(self) -> str:
        """Return the receiver's contribution to tree diagram."""
        return "{} ({}){}".format(
            self._tree_line_prefix(), self.iname(),
            "" if self._mandatory else "?")

class CaseNode(InternalNode):
    """Case node."""

    def _pattern_entry(self) -> SchemaPattern:
        return super()._schema_pattern()

    def _tree_line(self) -> str:
        """Return the receiver's contribution to tree diagram."""
        return "{}:({})".format(
            self._tree_line_prefix(), self.iname())

class LeafNode(DataNode, TerminalNode):
    """Leaf node."""

    def __init__(self):
        """Initialize the class instance."""
        super().__init__()
        self._mandatory = False # type: bool

    @property
    def mandatory(self) -> bool:
        """Is the receiver a mandatory node?"""
        return self._mandatory

    @property
    def default(self) -> Optional[ScalarValue]:
        """Default value of the receiver, if any."""
        if self.mandatory: return None
        if self._default is not None: return self._default
        return self.type.default

    def _post_process(self) -> None:
        super()._post_process()
        if self._mandatory:
            self.parent._add_mandatory_child(self)

    def _tree_line(self) -> str:
        return "{}{} <{}>".format(
            super()._tree_line(), "" if self._mandatory else "?", self.type)

    def _default_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        self._default = self.type.from_yang(stmt.argument, sctx)

class LeafListNode(SequenceNode, TerminalNode):
    """Leaf-list node."""

    @property
    def default(self) -> Optional[ScalarValue]:
        """Default value of the receiver, if any."""
        if self.mandatory: return None
        if self._default is not None: return self._default
        return (None if self.type.default is None
                else ArrayValue([self.type.default]))

    def _yang_class(self) -> str:
        return "leaf-list"

    def _check_list_props(self, inst: "InstanceNode") -> None:
        if (self.content_type() == ContentType.config and
            len(set(inst.value)) < len(inst.value)):
            raise SemanticError(inst, "non-unique leaf-list values")

    def _default_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        val = self.type.parse_value(stmt.argument)
        if self._default is None:
            self._default = ArrayValue([val])
        else:
            self._default.append(val)

    def _tree_line(self) -> str:
        return "{} <{}>".format(super()._tree_line(), self.type)

class AnyContentNode(DataNode):
    """Abstract class for anydata or anyxml nodes."""

    def __init__(self):
        """Initialize the class instance."""
        super().__init__()
        self._mandatory = False # type: bool

    def content_type(self) -> ContentType:
        """Override superclass method."""
        return TerminalNode.content_type(self)

    @property
    def mandatory(self) -> bool:
        """Is the receiver a mandatory node?"""
        return self._mandatory

    def from_raw(self, rval: RawValue, jptr: JSONPointer = "") -> Value:
        """Override the superclass method."""
        def convert(val):
            if isinstance(val, list):
                res = ArrayValue([convert(x) for x in val])
            elif isinstance(val, dict):
                res = ObjectValue({ x:convert(val[x]) for x in val })
            else:
                res = val
            return res
        return convert(rval)

    def _default_instance(self, pnode: "InstanceNode", ctype: ContentType,
                          lazy: bool = False) -> "InstanceNode":
        return pnode

    def _tree_line(self) -> str:
        return super()._tree_line() + ("" if self._mandatory else "?")

    def _ascii_tree(self, indent: str) -> str:
        return ""

    def _post_process(self) -> None:
        if self._mandatory:
            self.parent._add_mandatory_child(self)

class AnydataNode(AnyContentNode):
    """Anydata node."""
    pass

class AnyxmlNode(AnyContentNode):
    """Anyxml node."""
    pass

class RpcActionNode(GroupNode):
    """RPC or action node."""

    def __init__(self):
        """Initialize the class instance."""
        super().__init__()
        self._ctype = ContentType.nonconfig

    def _handle_substatements(self, stmt: Statement, sctx: SchemaContext) -> None:
        self._add_child(InputNode(self.ns))
        self._add_child(OutputNode(self.ns))
        super()._handle_substatements(stmt, sctx)

    def _flatten(self) -> List[SchemaNode]:
        return [self]

    def _tree_line_prefix(self) -> str:
        return super()._tree_line_prefix() + "-x"

    def _input_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        """Handle RPC or action input statement."""
        self.get_child("input")._handle_substatements(stmt, sctx)

    def _output_stmt(self, stmt: Statement, sctx: SchemaContext) -> None:
        """Handle RPC or action output statement."""
        self.get_child("output")._handle_substatements(stmt, sctx)

class InputNode(GroupNode):
    """RPC or action input node."""

    def __init__(self, ns):
        """Initialize the class instance."""
        super().__init__()
        self._config = False
        self.name = "input"
        self.ns = ns

    def _flatten(self) -> List[SchemaNode]:
        return [self]

    def _tree_line_prefix(self) -> str:
        return super()._tree_line_prefix() + "ro"

class OutputNode(GroupNode):
    """RPC or action output node."""

    def __init__(self, ns):
        """Initialize the class instance."""
        super().__init__()
        self._config = False
        self.name = "output"
        self.ns = ns

    def _flatten(self) -> List[SchemaNode]:
        return [self]

    def _tree_line_prefix(self) -> str:
        return super()._tree_line_prefix() + "ro"

class NotificationNode(GroupNode):
    """Notification node."""

    def __init__(self):
        """Initialize the class instance."""
        super().__init__()
        self._ctype = ContentType.nonconfig

    def _flatten(self) -> List[SchemaNode]:
        return [self]

    def _tree_line_prefix(self) -> str:
        return super()._tree_line_prefix() + "-n"

class SchemaNodeException(YangsonException):
    """Abstract exception class for schema node errors."""

    def __init__(self, sn: SchemaNode):
        self.schema_node = sn

    def __str__(self) -> str:
        return str(self.schema_node.qual_name)

class NonexistentSchemaNode(SchemaNodeException):
    """A schema node doesn't exist."""

    def __init__(self, sn: SchemaNode, name: YangIdentifier,
                 ns: YangIdentifier = None):
        super().__init__(sn)
        self.name = name
        self.ns = ns if ns else sn.ns

    def __str__(self) -> str:
        loc = ("under " + super().__str__() if self.schema_node.parent
                   else "top level")
        return loc + " – name '{}', namespace '{}'".format(self.name, self.ns)

class BadSchemaNodeType(SchemaNodeException):
    """A schema node is of a wrong type."""

    def __init__(self, sn: SchemaNode, expected: str):
        super().__init__(sn)
        self.expected = expected

    def __str__(self) -> str:
        return super().__str__() + " is not a " + self.expected

class BadLeafrefPath(SchemaNodeException):
    """A leafref path is incorrect."""
    pass

class RawDataError(YangsonException):
    """Abstract exception class for errors in raw data."""

    def __init__(self, jptr: JSONPointer):
        self.jptr = jptr

    def __str__(self) -> JSONPointer:
        return self.jptr

class RawMemberError(RawDataError):
    """Object member in the raw value doesn't exist in the schema."""
    pass

class RawTypeError(RawDataError):
    """Raw value is of an incorrect type."""

    def __init__(self, jptr: JSONPointer, detail: str):
        super().__init__(jptr)
        self.detail = detail

    def __str__(self):
        return "[{}] {}".format(self.jptr, self.detail)

class ValidationError(YangsonException):
    """Abstract exception class for instance validation errors."""

    def __init__(self, inst: "InstanceNode", detail: str):
        self.inst = inst
        self.detail = detail

    def __str__(self) -> str:
        return "[{}] {}".format(self.inst.json_pointer(), self.detail)

class SchemaError(ValidationError):
    """An instance violates a schema constraint."""
    pass

class SemanticError(ValidationError):
    """An instance violates a semantic rule."""
    pass

from .xpathast import Expr, LocationPath, Step, Root
from .instance import ArrayEntry, InstanceNode, NonexistentInstance