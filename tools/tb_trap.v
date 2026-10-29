// A testbench that prints a PASS token and THEN fails.
//
// Purpose: test whether run_sims.py can be fooled. Its verdict is
//     got = token in r.stdout
// with no check on xsim's exit code, so a token printed before a $fatal is
// indistinguishable from a clean pass.
//
// This is the defect the static runner had in round 26 (five checkers printed FAIL
// and returned 0). If this testbench is reported as PASS by the same logic, the
// simulation runner has the identical hole one level up.

`timescale 1ns / 1ps

module tb_trap;

    reg clk = 0;
    always #1 clk = ~clk;

    initial begin
        $display("starting");
        repeat (10) @(posedge clk);
        // Print the token, exactly as a real testbench would on success.
        $display("TRAP-PASS");
        repeat (10) @(posedge clk);
        // Then fail, as a monitor or a late assertion could.
        $display("TRAP-POST-TOKEN-ERROR");
        $fatal(1, "failure AFTER the pass token");
    end

    initial begin
        #400;
        $display("TRAP-TIMEOUT");
        $finish;
    end

endmodule
