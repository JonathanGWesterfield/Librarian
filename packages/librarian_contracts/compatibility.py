"""Descriptor-level compatibility checks for the versioned broker contract."""

from __future__ import annotations

from collections.abc import Iterable

from google.protobuf import descriptor_pb2


def find_breaking_changes(
    previous: descriptor_pb2.FileDescriptorProto,
    current: descriptor_pb2.FileDescriptorProto,
) -> list[str]:
    """Return additive-only v1 contract violations from ``previous`` to ``current``."""

    changes: list[str] = []
    _compare_file_identity(previous, current, changes)
    _compare_messages(previous.message_type, current.message_type, changes)
    _compare_enums(previous.enum_type, current.enum_type, changes)
    _compare_services(previous.service, current.service, changes)
    _check_required_fields(current.message_type, changes)
    return changes


def _compare_file_identity(
    previous: descriptor_pb2.FileDescriptorProto,
    current: descriptor_pb2.FileDescriptorProto,
    changes: list[str],
) -> None:
    for attribute in ("name", "package", "syntax"):
        old_value = getattr(previous, attribute)
        new_value = getattr(current, attribute)
        if old_value != new_value:
            changes.append(
                f"file {attribute} changed from {old_value!r} to {new_value!r}"
            )


def _compare_messages(
    previous: Iterable[descriptor_pb2.DescriptorProto],
    current: Iterable[descriptor_pb2.DescriptorProto],
    changes: list[str],
) -> None:
    current_by_name = {message.name: message for message in current}
    for old_message in previous:
        new_message = current_by_name.get(old_message.name)
        if new_message is None:
            changes.append(f"message {old_message.name} was removed")
            continue
        _compare_message(old_message, new_message, changes)


def _compare_message(
    previous: descriptor_pb2.DescriptorProto,
    current: descriptor_pb2.DescriptorProto,
    changes: list[str],
) -> None:
    context = f"message {previous.name}"
    previous_fields = {field.number: field for field in previous.field}
    current_fields = {field.number: field for field in current.field}
    for number, old_field in previous_fields.items():
        new_field = current_fields.get(number)
        if new_field is None:
            changes.append(f"{context} removed field {old_field.name} ({number})")
            continue
        if _field_signature(old_field) != _field_signature(new_field):
            changes.append(
                f"{context} changed field {old_field.name} ({number}) from "
                f"{_field_signature(old_field)!r} to {_field_signature(new_field)!r}"
            )

    _check_reserved_ranges(
        context,
        previous.reserved_range,
        current.reserved_range,
        current_fields,
        changes,
    )
    _check_reserved_names(
        context, previous.reserved_name, current.reserved_name, changes
    )
    _compare_messages(previous.nested_type, current.nested_type, changes)
    _compare_enums(previous.enum_type, current.enum_type, changes)


def _field_signature(
    field: descriptor_pb2.FieldDescriptorProto,
) -> tuple[object, ...]:
    return (
        field.name,
        field.label,
        field.type,
        field.type_name,
        field.extendee,
        field.default_value,
        field.proto3_optional,
        field.HasField("oneof_index"),
        field.oneof_index if field.HasField("oneof_index") else None,
    )


def _compare_enums(
    previous: Iterable[descriptor_pb2.EnumDescriptorProto],
    current: Iterable[descriptor_pb2.EnumDescriptorProto],
    changes: list[str],
) -> None:
    current_by_name = {enum.name: enum for enum in current}
    for old_enum in previous:
        new_enum = current_by_name.get(old_enum.name)
        if new_enum is None:
            changes.append(f"enum {old_enum.name} was removed")
            continue

        current_values = {value.number: value for value in new_enum.value}
        for old_value in old_enum.value:
            new_value = current_values.get(old_value.number)
            if new_value is None:
                changes.append(
                    f"enum {old_enum.name} removed value {old_value.name} ({old_value.number})"
                )
            elif new_value.name != old_value.name:
                changes.append(
                    f"enum {old_enum.name} changed value {old_value.number} from "
                    f"{old_value.name} to {new_value.name}"
                )

        _check_reserved_ranges(
            f"enum {old_enum.name}",
            old_enum.reserved_range,
            new_enum.reserved_range,
            current_values,
            changes,
        )
        _check_reserved_names(
            f"enum {old_enum.name}",
            old_enum.reserved_name,
            new_enum.reserved_name,
            changes,
        )


def _compare_services(
    previous: Iterable[descriptor_pb2.ServiceDescriptorProto],
    current: Iterable[descriptor_pb2.ServiceDescriptorProto],
    changes: list[str],
) -> None:
    current_by_name = {service.name: service for service in current}
    for old_service in previous:
        new_service = current_by_name.get(old_service.name)
        if new_service is None:
            changes.append(f"service {old_service.name} was removed")
            continue

        current_methods = {method.name: method for method in new_service.method}
        for old_method in old_service.method:
            new_method = current_methods.get(old_method.name)
            if new_method is None:
                changes.append(
                    f"service {old_service.name} removed method {old_method.name}"
                )
                continue
            old_signature = (
                old_method.input_type,
                old_method.output_type,
                old_method.client_streaming,
                old_method.server_streaming,
            )
            new_signature = (
                new_method.input_type,
                new_method.output_type,
                new_method.client_streaming,
                new_method.server_streaming,
            )
            if old_signature != new_signature:
                changes.append(
                    f"service {old_service.name} changed method {old_method.name} from "
                    f"{old_signature!r} to {new_signature!r}"
                )


def _check_reserved_ranges(
    context: str,
    previous: Iterable[descriptor_pb2.DescriptorProto.ReservedRange],
    current: Iterable[descriptor_pb2.DescriptorProto.ReservedRange],
    current_values: dict[int, object],
    changes: list[str],
) -> None:
    current_ranges = {(item.start, item.end) for item in current}
    for old_range in previous:
        old_bounds = (old_range.start, old_range.end)
        if old_bounds not in current_ranges:
            changes.append(f"{context} removed reserved range {old_bounds}")
        for number in range(old_range.start, old_range.end):
            if number in current_values:
                changes.append(f"{context} reused reserved number {number}")


def _check_reserved_names(
    context: str,
    previous: Iterable[str],
    current: Iterable[str],
    changes: list[str],
) -> None:
    current_names = set(current)
    for name in previous:
        if name not in current_names:
            changes.append(f"{context} removed reserved name {name}")


def _check_required_fields(
    messages: Iterable[descriptor_pb2.DescriptorProto], changes: list[str]
) -> None:
    for message in messages:
        for field in message.field:
            if field.label == descriptor_pb2.FieldDescriptorProto.LABEL_REQUIRED:
                changes.append(
                    f"message {message.name} uses forbidden required field {field.name}"
                )
        _check_required_fields(message.nested_type, changes)
