`timescale 1ns / 1ps
// Behavioral smoke test for smoke_top.
module tb_smoke;

    reg        sys_clk = 1'b0;
    reg        rst_n   = 1'b0;
    wire [3:0] led;

    smoke_top dut (
        .sys_clk (sys_clk),
        .rst_n   (rst_n),
        .led     (led)
    );

    // 100 MHz stimulus
    always #5 sys_clk = ~sys_clk;

    initial begin
        $display("[tb] start");
        #100 rst_n = 1'b1;
        #500;
        if (^led === 1'bx) begin
            $fatal(1, "[tb] FAIL: led is X");
        end
        if (led !== 4'b0001) begin
            $fatal(1, "[tb] FAIL: led=%b expected 0001 after reset", led);
        end
        $display("[tb] led=%b", led);
        $display("[tb] PASS");
        $finish;
    end

endmodule