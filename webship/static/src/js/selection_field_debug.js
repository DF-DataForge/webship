/** @odoo-module **/
import { SelectionField } from "@web/views/fields/selection/selection_field";
import { patch } from "@web/core/utils/patch";

patch(SelectionField.prototype, {
    get string() {
        try {
            return super.string;
        } catch (e) {
            const value = this.props.record.data[this.props.name];
            console.warn(
                `[webship] SelectionField: unknown value "${value}" ` +
                `(type: ${typeof value}) for field "${this.props.name}" ` +
                `on ${this.props.record.resModel} ID=${this.props.record.resId}`
            );
            return "";
        }
    },
});
