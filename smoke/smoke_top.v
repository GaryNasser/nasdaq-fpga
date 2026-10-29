`timescale 1ns / 1ps
// Minimal smoke-test design: free-running LED rotator.
module smoke_top (
    input  wire       sys_clk,   // 125 MHz on PYNQ-Z2 (H16)
    input  wire       rst_n,     // BTN0 (D19)
    output reg  [3:0] led        // LD0..LD3
);

    reg [23:0] div_cnt;

    always @(posedge sys_clk) begin
        if (!rst_n) begin
            div_cnt <= 24'd0;
            led     <= 4'b0001;
        end else begin
            div_cnt <= div_cnt + 24'd1;
            if (div_cnt == 24'hFFFFFF)
                led <= {led[2:0], led[3]};
        end
    end

endmodule